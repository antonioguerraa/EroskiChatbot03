from langgraph.types import Command
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import asyncpg
from datetime import datetime
import logging

from config.settings import get_settings
from models.eroski_state import EroskiState
from nodes.base_node import BaseNode
from utils.llm.providers import get_llm
import json
from nodes.tools.confirmation_tool import add_confirmation_tool_to_node

@add_confirmation_tool_to_node
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
{{datos_actuales}}

El usuario ha dicho:
{{mensaje_usuario}}

¿El usuario quiere modificar alguno de sus datos (nombre, apellido, tienda, sección)?
Responde solo con "modificar" o "continuar".
            """),
        ])

        # Prompt para extraer datos del mensaje
        self.extraccion_prompt = None  # Se construye dinámicamente en execute porque depende de tiendas


    async def execute(self, state: EroskiState) -> Command:
        # 1. Obtener mensaje del usuario
        print("👹RecogerDatosEmpleadoNode👹")
        messages = state.get("messages", [])
        ultimo_msg = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        if not ultimo_msg:
            return self._respuesta_ai("Hola, ¿cómo te llamas?")

        mensaje_usuario = ultimo_msg.content.strip()

        #verifica si hay alguna confirmación pendiente
        if state.get("modificaciones_pendientes"):
            print(f"modifaciones: {state.get('modificaciones_pendientes')}")
            return self._pending_confirmation(state, mensaje_usuario)
        
        #verificar si hay alguna modificacion en el estado

        
        # 2. Cargar tiendas si aún no está hecho
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



        nuevo_estado = state.copy()
        nuevo_estado["last_activity"] = datetime.now()
        datos_extraidos = self._llm_extraccion(datos_actuales, mensaje_usuario)

        resultado_confirmacion = self._detectar_cambios(state, datos_extraidos)

        if isinstance(resultado_confirmacion, Command):
            return resultado_confirmacion  # Salimos del nodo pidiendo confirmación
        
        if any(valor is not None for valor in datos_extraidos.values()):
            
            return self._actualizar_estado(nuevo_estado, datos_extraidos)
            
        if intencion == "modificar":
            # 4. Actualizar estado con los datos extraídos
            if datos_extraidos.get("nombre"): nuevo_estado["employee_name"] = datos_extraidos["nombre"]
            if datos_extraidos.get("apellido"): nuevo_estado["employee_lastname"] = datos_extraidos["apellido"]
            if datos_extraidos.get("tienda"): nuevo_estado["incident_store_name"] = datos_extraidos["tienda"]
            if datos_extraidos.get("seccion"): nuevo_estado["incident_department"] = datos_extraidos["seccion"]
            resumen = (
                    f"✅ He actualizado tus datos:\n\n"
                    f"👤 {nuevo_estado.get('employee_name', 'No especificado')} {nuevo_estado.get('employee_lastname', '')}\n"
                    f"🏬 Tienda: {nuevo_estado.get('incident_store_name', 'No especificada')}\n"
                    f"🧭 Sección: {nuevo_estado.get('incident_department', 'No especificada')}\n\n"
                    "¿Es correcto? ¿Quieres modificar algo más?"
                )
            return Command(update={
                "messages":[AIMessage(content=resumen)],
                    "current_node": "identificar_incidencia",
                    "authenticated": False,
                    'awaiting_user_input': True
                })
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
                return Command(update={
                    "messages":[AIMessage(content=resumen)],
                    "current_node": "identificar_incidencia",
                    "authenticated": False,
                    'awaiting_user_input': True
                })
            else:
                faltan = []
                if not nuevo_estado.get("employee_name"): faltan.append("tu nombre")
                if not nuevo_estado.get("employee_lastname"): faltan.append("tu apellido")
                if not nuevo_estado.get("incident_store_name"): faltan.append("la tienda donde trabajas")
                if not nuevo_estado.get("incident_department"): faltan.append("tu sección")
                print(f"Faltan datos: {faltan}")
                pregunta = "¿Podrías decirme " + " y ".join(faltan) + "?"
                return Command(update={
                    "messages":[AIMessage(content=pregunta)],
                    "current_node": "identificar_incidencia",
                    "authenticated": False,
                    'awaiting_user_input': True
                })

        else:
            # Fallback en caso de respuesta inesperada
            self.logger.warning(f"Respuesta de intención inesperada: {intencion}")
            pregunta = "No he entendido si quieres modificar tus datos o continuar. ¿Podrías aclararlo?"
            return Command(update={
                    "messages":[AIMessage(content=pregunta)],
                    "current_node": "identificar_incidencia",
                    "authenticated": False,
                    'awaiting_user_input': True

                })

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
        return Command(update={"messages": [AIMessage(content=texto)],
                    "current_node": "identificar_incidencia",
                    "authenticated": False,
                    'awaiting_user_input': True})

    def get_required_fields(self) -> list[str]:
        """Devuelve los campos mínimos requeridos para que el nodo funcione."""
        return ["messages", "session_id"]

    def get_actor_description(self) -> str:
        """Descripción del actor para trazas/logs"""
        return "Nodo encargado de recoger los datos básicos del empleado"
    
    def _llm_extraccion(self, datos_actuales: Dict[str, Optional[str]], mensaje_usuario: str) -> dict:
        
        class datos_salida(BaseModel):
            nombre: Optional[str] = Field(description="Nombre de la persona")
            apellido: Optional[str] = Field(description="Apellido de la persona")
            tienda: Optional[str] = Field(description="Tienda donde se produce la incidencia")
            seccion: Optional[str] = Field(description="Departamento donde se produce la incidencia")
        
        parser = JsonOutputParser(pydantic_object=datos_salida)
        datos_actuales_text = "\n".join([f"- {k}: {v}" for k, v in datos_actuales.items()])

        system_prompt = f"""
                Eres un asistente de Eroski que debes extraer 4 campos del mensaje del usuario:
                - nombre
                - apellido
                - tienda (de esta lista: {', '.join(self.tiendas[:20])})
                - seccion (Carnicería, Pescadería, Panadería, Caja, etc)

                Los datos actuales son:
                {datos_actuales_text}

                Si no encuentras un dato, ponlo como null.
                Si el usuario quiere modificar algún dato, actualízalo. Si no, mantenlos igual.

                Responde con JSON que contenga el nombre, apellido, tienda y sección.
            """
        extraccion_prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}")
        ])
        chain = extraccion_prompt | self.llm | parser
        try:
            respuesta = chain.invoke({"input": mensaje_usuario})
            #data = self._parsear_respuesta(respuesta.content)
            data = respuesta
        except Exception as e:
            self.logger.warning(f"❌ Error interpretando mensaje: {e}")
            return self._respuesta_ai("No he entendido tu mensaje. ¿Podrías repetirlo más claramente?")
        # Si `self.llm` devuelve texto plano JSON, conviértelo:
        return data
    
    def _actualizar_estado(self, estado: EroskiState, datos_extraidos: dict) -> Command:
        """Actualiza el estado con los datos extraídos con el LLM si algún campo estaba vacío y ahora puede rellenarse."""

        mapeo = {
            "employee_name": "nombre",
            "employee_lastname": "apellido",
            "incident_store_name": "tienda",
            "incident_department": "seccion"
        }

        actualizar = {
            campo_estado: datos_extraidos[campo_llm]
            for campo_estado, campo_llm in mapeo.items()
            if not estado.get(campo_estado) and datos_extraidos.get(campo_llm)
        }

        faltan = [
            campo_llm
            for campo_estado, campo_llm in mapeo.items()
            if not estado.get(campo_estado) and not datos_extraidos.get(campo_llm)
        ]

        etiquetas_legibles = {
            "nombre": "nombre",
            "apellido": "apellido",
            "tienda": "tienda",
            "seccion": "departamento"
        }

        mensaje = None

        if actualizar and faltan:
            # Caso 1: actualizo y aún falta algo → pregunto lo que falta
            campos_pendientes = [etiquetas_legibles[c] for c in faltan]
            lista = (
                " y ".join([", ".join(campos_pendientes[:-1]), campos_pendientes[-1]])
                if len(campos_pendientes) > 2
                else " y ".join(campos_pendientes)
            )
            mensaje = f"Muy bien. ¿Me puedes proporcionar el {lista}?"
            update = {**actualizar, "messages": [AIMessage(content=mensaje)]}
            return Command(update=update)

        elif actualizar and not faltan:
            # Caso 2: todo extraído → mensaje de cierre
            mensaje = "Perfecto, ya tengo todos los datos. Gracias."
            
            update = {**actualizar, 
                      "messages": [AIMessage(content=mensaje)],
                      "authenticated": True
                      }

            return Command(update=update)

        elif not actualizar and faltan:
            # Caso 3: no puedo actualizar nada, pero sé lo que falta → pregunto directamente
            campos_pendientes = [etiquetas_legibles[c] for c in faltan]
            lista = (
                " y ".join([", ".join(campos_pendientes[:-1]), campos_pendientes[-1]])
                if len(campos_pendientes) > 2
                else " y ".join(campos_pendientes)
            )
            mensaje = f"¿Me puedes proporcionar el {lista}?"
            return Command(update={"messages": [AIMessage(content=mensaje)]})

        else:
            # Caso 4: no hubo extracción útil ni faltantes detectables
            self.logger.info("ℹ️ No se han actualizado datos ni hay campos pendientes.")
            return None

    def _detectar_cambios(self, estado: EroskiState, datos_extraidos: dict) -> Optional[Command] | Dict:
        # Obtener datos actuales
        mapeo = {
            "employee_name": "nombre",
            "employee_lastname": "apellido",
            "incident_store_name": "tienda",
            "incident_department": "seccion"
        }
        
        modificados={}
        for campo_estado, campo_llm in mapeo.items():
            if datos_extraidos.get(campo_llm) and datos_extraidos.get(campo_llm) != estado.get(campo_estado) and estado.get(campo_estado):
                modificados[campo_estado] = datos_extraidos[campo_llm]
        
        """modificados = {
            campo_estado: datos_extraidos[campo_llm]
            for campo_estado, campo_llm in mapeo.items()
            if not datos_extraidos.get(campo_llm) and datos_extraidos.get(campo_llm) != estado.get(campo_estado)
        }"""

        etiquetas_legibles = {
            "employee_name": "nombre",
            "employee_lastname": "apellido",
            "incident_store_name": "tienda",
            "incident_department": "departamento"
        }

        if modificados:
            partes = [
                f"{etiquetas_legibles[campo]} es {valor}"
                for campo, valor in modificados.items()
            ]
            texto = ", ".join(partes[:-1]) + f" y {partes[-1]}" if len(partes) > 1 else partes[0]
            mensaje_confirmacion = f"He entendido que {texto}. ¿Puedes confirmarlo, por favor?"
            return Command(update={
                "pending_confirmation": True,
                "modificaciones_pendientes": modificados,
                "messages": [AIMessage(content=mensaje_confirmacion)]
            })

    def _pending_confirmation(self, estado:EroskiState, mensaje_usuario:str) -> Command:
        if estado.get("pending_confirmation"):
            resultado = self.check_confirmation(mensaje_usuario)
            
            if resultado == "si":
                return Command(update={
                    **estado.get("modificaciones_pendientes", {}),
                    "pending_confirmation": None,
                    "modificaciones_pendientes": None,
                    "messages": [AIMessage(content="Perfecto, ya he actualizado los datos.")]
                })
            elif resultado == "no":
                return Command(update={
                    "pending_confirmation": None,
                    "modificaciones_pendientes": None,
                    "messages": [AIMessage(content="De acuerdo, no haré ningún cambio.")]
                })
            else:
                return Command(update={
                    "messages": [AIMessage(content="¿Podrías confirmarlo con un sí o un no?")]
                })


# =============================================================================
# FUNCIÓN WRAPPER PARA LANGGRAPH
# =============================================================================

async def recoger_datos_empleado_node(state: EroskiState) -> Command:
    """
    Función wrapper para LangGraph - Nodo Identificador Base de Datos
    
    Args:
        state: Estado actual como EroskiState
        
    Returns:
        Command con las actualizaciones de estado
    """
    # Crear instancia del nodo
    node = RecogerDatosEmpleadoNode()
    
    # Ejecutar el nodo
    return await node.execute(state)