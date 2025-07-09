import json
from langgraph.types import Command
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from typing import List, Dict, Optional
import asyncpg
from datetime import datetime
import logging

from config.settings import get_settings
from models.eroski_state import EroskiState
from nodes.base_node import BaseNode
from utils.llm.providers import get_llm


class RecogerDatosEmpleadoNode(BaseNode):
    def __init__(self):
        super().__init__("RecogerDatosEmpleado")
        self.llm = get_llm()
        self.logger = logging.getLogger("RecogerDatosEmpleadoNode")
        self.tiendas = []

        # Prompt para detectar intención de modificar o continuar
        self.intencion_prompt = ChatPromptTemplate.from_messages([
            ("system", """
Eres un asistente que detecta la intención del usuario respecto a sus datos personales.
Los datos actuales del usuario son:
{datos_actuales}

El usuario ha dicho:
{mensaje_usuario}

¿El usuario quiere modificar alguno de sus datos (nombre, apellido, tienda, sección)?
Responde solo con "modificar" o "continuar".
            """),
        ])

        # Prompt para extraer datos del mensaje
        self.extraccion_prompt = None  # Se construye dinámicamente en execute porque depende de tiendas

    async def execute(self, state: EroskiState) -> Command:
        messages = state.get("messages", [])
        print(f"🙋‍♀️{messages}")
        ultimo_msg = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        if not ultimo_msg:
            return self._respuesta_ai("Hola, ¿cómo te llamas?")

        mensaje_usuario = ultimo_msg.content.strip()

        if not self.tiendas:
            self.tiendas = await self._cargar_tiendas()

        datos_actuales = {
            "nombre": state.get("employee_name"),
            "apellido": state.get("employee_lastname"),
            "tienda": state.get("incident_store_name"),
            "seccion": state.get("incident_department"),
        }

        # 1. Detectar intención con LLM
        intencion_chain = self.intencion_prompt | self.llm
        try:
            intencion_response = await intencion_chain.ainvoke({
                "datos_actuales": json.dumps(datos_actuales, ensure_ascii=False),
                "mensaje_usuario": mensaje_usuario,
            })
            intencion = intencion_response.content.strip().lower()
        except Exception as e:
            self.logger.warning(f"❌ Error detectando intención: {e}")
            intencion = "continuar"  # fallback seguro

        # 2. Construir prompt de extracción con tiendas
        self.extraccion_prompt = ChatPromptTemplate.from_messages([
            ("system", f"""
Eres un asistente de Eroski que debe extraer 4 campos del mensaje del usuario:
- nombre
- apellido
- tienda (de esta lista: {', '.join(self.tiendas[:20])})
- seccion (Carnicería, Pescadería, Panadería, Caja, etc)

Los datos actuales son:
{json.dumps(datos_actuales, ensure_ascii=False)}

Si el usuario quiere modificar algún dato, actualízalo. Si no, mantenlos igual.
Si algún campo no está en el mensaje, ponlo como null.

Responde en JSON:
{{"nombre": ..., "apellido": ..., "tienda": ..., "seccion": ...}}
            """),
            ("human", "{input}")
        ])
        extraccion_chain = self.extraccion_prompt | self.llm

        nuevo_estado = state.copy()
        nuevo_estado["last_activity"] = datetime.now()

        if intencion == "modificar":
            try:
                response = await extraccion_chain.ainvoke({"input": mensaje_usuario})
                data = self._parsear_respuesta(response.content)
            except Exception as e:
                self.logger.warning(f"❌ Error interpretando mensaje: {e}")
                return self._respuesta_ai("No he entendido tu mensaje. ¿Podrías repetirlo más claramente?")

            # Actualizar datos solo si vienen no nulos
            if data.get("nombre") is not None: nuevo_estado["employee_name"] = data["nombre"]
            if data.get("apellido") is not None: nuevo_estado["employee_lastname"] = data["apellido"]
            if data.get("tienda") is not None: nuevo_estado["incident_store_name"] = data["tienda"]
            if data.get("seccion") is not None: nuevo_estado["incident_department"] = data["seccion"]

            resumen = (
                f"✅ He actualizado tus datos:\n\n"
                f"👤 {nuevo_estado.get('employee_name', 'No especificado')} {nuevo_estado.get('employee_lastname', '')}\n"
                f"🏬 Tienda: {nuevo_estado.get('incident_store_name', 'No especificada')}\n"
                f"🧭 Sección: {nuevo_estado.get('incident_department', 'No especificada')}\n\n"
                "¿Es correcto? ¿Quieres modificar algo más?"
            )
            nuevo_estado["messages"] = messages + [AIMessage(content=resumen)]
            return Command(update=nuevo_estado)

        elif intencion == "continuar":
            # Verificar si datos completos
            campos = ["employee_name", "employee_lastname", "incident_store_name", "incident_department"]
            if all(nuevo_estado.get(campo) for campo in campos):
                resumen = (
                    f"✅ Te he identificado:\n\n"
                    f"👤 {nuevo_estado['employee_name']} {nuevo_estado['employee_lastname']}\n"
                    f"🏬 Tienda: {nuevo_estado['incident_store_name']}\n"
                    f"🧭 Sección: {nuevo_estado['incident_department']}\n\n"
                    "¿En qué puedo ayudarte?"
                )
                nuevo_estado["authenticated"] = True
                nuevo_estado["current_node"] = "classify_query"
                nuevo_estado["messages"] = messages + [AIMessage(content=resumen)]
                return Command(update=nuevo_estado)
            else:
                faltan = []
                if not nuevo_estado.get("employee_name"): faltan.append("tu nombre")
                if not nuevo_estado.get("employee_lastname"): faltan.append("tu apellido")
                if not nuevo_estado.get("incident_store_name"): faltan.append("la tienda donde trabajas")
                if not nuevo_estado.get("incident_department"): faltan.append("tu sección")

                pregunta = "¿Podrías decirme " + " y ".join(faltan) + "?"
                nuevo_estado["messages"] = messages + [AIMessage(content=pregunta)]
                return Command(update=nuevo_estado)

        else:
            # Fallback en caso de respuesta inesperada
            self.logger.warning(f"Respuesta de intención inesperada: {intencion}")
            pregunta = "No he entendido si quieres modificar tus datos o continuar. ¿Podrías aclararlo?"
            nuevo_estado["messages"] = messages + [AIMessage(content=pregunta)]
            return Command(update=nuevo_estado)

    async def _cargar_tiendas(self) -> List[str]:
        try:
            conn = await asyncpg.connect(get_settings().database.connection_string)
            rows = await conn.fetch("SELECT nombre_tienda FROM maestro_tiendas ORDER BY nombre_tienda")
            await conn.close()
            return [row["nombre_tienda"] for row in rows]
        except Exception as e:
            self.logger.error(f"❌ Error cargando tiendas: {e}")
            return ["Hipermercado Bilbondo", "Center Durango", "Eroski Gernika"]

    def _parsear_respuesta(self, texto: str) -> Dict[str, Optional[str]]:
        import json
        if "```" in texto:
            texto = texto.strip("```json").strip("```")
        return json.loads(texto)

    def _respuesta_ai(self, texto: str) -> Command:
        return Command(update={"messages": [AIMessage(content=texto)], "current_node": "recoger_datos"})

    def get_required_fields(self) -> list[str]:
        return ["messages", "session_id"]

    def get_actor_description(self) -> str:
        return "Nodo encargado de recoger los datos básicos del empleado"


# Wrapper para LangGraph

async def recoger_datos_empleado_node(state: EroskiState) -> Command:
    node = RecogerDatosEmpleadoNode()
    return await node.execute(state)
