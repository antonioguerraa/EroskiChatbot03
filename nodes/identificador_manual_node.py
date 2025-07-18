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
        print("👹🏅🏅RecogerDatosEmpleadoNode simplificado con control de intentos🏅🏅👹")

        messages = state.get("messages", [])
        ultimo_msg = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        if not ultimo_msg:
            return self._respuesta_ai("Hola, ¿cómo te llamas?")

        mensaje_usuario = ultimo_msg.content.strip()

        if state.get("modificaciones_pendientes"):
            return self._pending_confirmation(state, mensaje_usuario)

        if not self.tiendas:
            self.tiendas = await self._cargar_tiendas()

        datos_actuales = {
            "nombre": state.get("incident_user_name"),
            "apellido": state.get("incident_last_name"),
            "tienda": state.get("incident_store_name"),
            "seccion": state.get("incident_department"),
            "tienda_tentativa": state.get("tienda_tentativa"),
        }

        intento_tienda = state.get("intento_tienda", 0)
        intentos_identificar_usuario = state.get("intentos_identificar_usuario", 0)

        print(f"👹intento_tienda: {intento_tienda}")
        datos_extraidos = self._llm_extraccion(
            datos_actuales,
            mensaje_usuario,
            intentos_identificar_usuario,
            intento_tienda
        )

        nuevo_estado = state.copy()
        nuevo_estado["last_activity"] = datetime.now()
        nuevo_estado["intentos_identificar_usuario"] = intentos_identificar_usuario + 1

        if isinstance(datos_extraidos, Command):
            return datos_extraidos

        tienda_llm = datos_extraidos.get("tienda")
        tienda_tentativa = datos_extraidos.get("tienda_tentativa")
        tienda_identificada = tienda_llm in self.tiendas if tienda_llm else False

        # Actualización de campos extraídos
        if datos_extraidos.get("nombre"):
            nuevo_estado["incident_user_name"] = datos_extraidos["nombre"]
        if datos_extraidos.get("apellido"):
            nuevo_estado["incident_last_name"] = datos_extraidos["apellido"]
        if datos_extraidos.get("seccion"):
            nuevo_estado["incident_department"] = datos_extraidos["seccion"]
        if datos_extraidos.get("authenticated"):
            print(f"authenticated: {datos_extraidos['authenticated']}")
            nuevo_estado["Authenticated"] = datos_extraidos["authenticated"]
            

        print(f"👹tienda_llm: {tienda_llm}, \
                \ntienda_identificada: {tienda_identificada}, \
                \nintento_tienda: {intento_tienda}, \
                \ntienda_tentativa: {tienda_tentativa},\
                \ntienda_tentativa: {tienda_tentativa},\
                \nauthenticated: {datos_extraidos['authenticated']}, \
                \nrespuesta: {datos_extraidos['respuesta']}")
        






        # 🚨 Control de tienda tentativa e intentos
        if not tienda_llm and tienda_tentativa:
            intento_tienda += 1
            print("")
            nuevo_estado["intento_tienda"] = intento_tienda
            nuevo_estado["tienda_tentativa"] = tienda_tentativa

            if intento_tienda >= 3:
                nuevo_estado["incident_store_name"] = tienda_tentativa
                nuevo_estado["tienda_identificada"] = False
                nuevo_estado["tienda_tentativa"] = tienda_tentativa

                # ⚠️ Forzamos autenticación si ya están todos los campos
                if nuevo_estado.get("incident_user_name") and nuevo_estado.get("incident_last_name") and nuevo_estado.get("incident_department"):
                    nuevo_estado["authenticated"] = True

                return Command(update={
                    **nuevo_estado,
                    "messages": [AIMessage(content=datos_extraidos.get("respuesta", f"He guardado la tienda '{tienda_llm}' como válida. Vamos ahora con la incidencia."))],
                    "current_node": "identificar_incidencia",
                    "awaiting_user_input": True
                })

        elif tienda_llm and tienda_identificada:
            nuevo_estado["incident_store_name"] = tienda_llm
            nuevo_estado["tienda_identificada"] = True
            nuevo_estado["tienda_tentativa"] = None
            nuevo_estado["intento_tienda"] = 0

        
        # ✅ Si ya tenemos todos los datos, autenticamos
        if (
            nuevo_estado.get("incident_user_name")
            and nuevo_estado.get("incident_last_name")
            and nuevo_estado.get("incident_department")
            and nuevo_estado.get("incident_store_name")
        ):
            nuevo_estado["authenticated"] = True

        return Command(update={
            **nuevo_estado,
            "messages": [AIMessage(content=datos_extraidos.get("respuesta", "Gracias. Vamos ahora con la incidencia."))],
            "current_node": "identificar_incidencia",
            "awaiting_user_input": True
        })



    async def execute_kk2(self, state: EroskiState) -> Command:
        print("👹🏅🏅RecogerDatosEmpleadoNode🏅🏅👹")
        messages = state.get("messages", [])
        ultimo_msg = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        if not ultimo_msg:
            return self._respuesta_ai("Hola, ¿cómo te llamas?")

        mensaje_usuario = ultimo_msg.content.strip()

        if state.get("modificaciones_pendientes"):
            print(f"modifaciones: {state.get('modificaciones_pendientes')}")
            return self._pending_confirmation(state, mensaje_usuario)

        #se cargan las tiendas de la base de datos.
        if not self.tiendas:
            self.tiendas = await self._cargar_tiendas()

        # datos recopilados hasta ahora
        datos_actuales = {
            "nombre": state.get("incident_user_name"),
            "apellido": state.get("incident_last_name"),
            "tienda": state.get("incident_store_name"),
            "seccion": state.get("incident_department"),
            "tienda_tentativa": state.get("tienda_tentativa"),
            
        }

        intencion_chain = self.intencion_prompt | self.llm
        try:
            intencion_response = await intencion_chain.ainvoke({
                "datos_actuales": json.dumps(datos_actuales, ensure_ascii=False),
                "mensaje_usuario": mensaje_usuario,
            })
            intencion = intencion_response.content.strip().lower()
            print(f"👹intencion: {intencion}")
        except Exception as e:
            self.logger.warning(f"❌ Error detectando intención: {e}")
            intencion = "continuar"

        nuevo_estado = state.copy()
        nuevo_estado["last_activity"] = datetime.now()
        intento_tienda = nuevo_estado.get("intento_tienda",0)
        intentos_identificar_usuario = nuevo_estado.get("intentos_identificar_usuario",0)
        datos_extraidos = self._llm_extraccion(datos_actuales, 
                                               mensaje_usuario,
                                               intentos_identificar_usuario,
                                               intento_tienda,
                                               )
        nuevo_estado["intentos_identificar_usuario"] = intentos_identificar_usuario + 1

        if isinstance(datos_extraidos, Command):
            return datos_extraidos


        print(f"👹datos_extraidos: {datos_extraidos}")
        resultado_confirmacion = self._detectar_cambios(state, datos_extraidos)
        print(f"👹resultado_confirmacion: {resultado_confirmacion}")

        if isinstance(resultado_confirmacion, Command):
            return resultado_confirmacion

        if any(valor is not None for valor in datos_extraidos.values()):
            return self._actualizar_estado(nuevo_estado, datos_extraidos)

        if intencion == "modificar":
            if datos_extraidos.get("nombre"):
                nuevo_estado["incident_user_name"] = datos_extraidos["nombre"]
            if datos_extraidos.get("apellido"):
                nuevo_estado["incident_last_name"] = datos_extraidos["apellido"]
            if datos_extraidos.get("tienda") and datos_extraidos["tienda"] in self.tiendas:
                nuevo_estado["incident_store_name"] = datos_extraidos["tienda"]
            if datos_extraidos.get("seccion"):
                nuevo_estado["incident_department"] = datos_extraidos["seccion"]

            resumen = (
                f"✅ He actualizado tus datos:\n\n"
                f"👤 {nuevo_estado.get('incident_user_name', 'No especificado')} {nuevo_estado.get('incident_last_name', '')}\n"
                f"🏬 Tienda: {nuevo_estado.get('incident_store_name', 'No especificada')}\n"
                f"🧭 Sección: {nuevo_estado.get('incident_department', 'No especificada')}\n\n"
                "¿Es correcto? ¿Quieres modificar algo más?"
            )
            return Command(update={
                "messages": [AIMessage(content=resumen)],
                "current_node": "identificar_incidencia",
                "authenticated": False,
                "awaiting_user_input": True
            })

        elif intencion == "continuar":
            campos_faltantes = []
            if not nuevo_estado.get("incident_user_name"):
                campos_faltantes.append("tu nombre")
            if not nuevo_estado.get("incident_last_name"):
                campos_faltantes.append("tu apellido")
            if not nuevo_estado.get("incident_store_name"):
                campos_faltantes.append("la tienda donde trabajas")
            if not nuevo_estado.get("incident_department"):
                campos_faltantes.append("tu sección")

            if not campos_faltantes:
                resumen = (
                    f"✅ Te he identificado:\n\n"
                    f"👤 {nuevo_estado['incident_user_name']} {nuevo_estado['incident_last_name']}\n"
                    f"🏬 Tienda: {nuevo_estado['incident_store_name']}\n"
                    f"🧭 Sección: {nuevo_estado['incident_department']}\n\n"
                    "¿En qué puedo ayudarte?"
                )
                return Command(update={
                    "messages": [AIMessage(content=resumen)],
                    "current_node": "identificar_incidencia",
                    "authenticated": False,
                    "awaiting_user_input": True
                })
            else:
                self.logger.info(f"ℹ️ Faltan aún los siguientes datos: {campos_faltantes}")
                pregunta = "¿Podrías decirme " + " y ".join(campos_faltantes) + "?"
                return Command(update={
                    "messages": [AIMessage(content=pregunta)],
                    "current_node": "identificar_incidencia",
                    "authenticated": False,
                    "awaiting_user_input": True
                })

        else:
            self.logger.warning(f"Respuesta de intención inesperada: {intencion}")
            return Command(update={
                "messages": [AIMessage(content="No he entendido si quieres modificar tus datos o continuar. ¿Podrías aclararlo?")],
                "current_node": "identificar_incidencia",
                "authenticated": False,
                "awaiting_user_input": True
            })


#========================================
#========================================
#========================================




    async def execute_kk(self, state: EroskiState) -> Command:
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
            "nombre": state.get("incident_user_name"),
            "apellido": state.get("incident_last_name"),
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
            print(f"👹intencion: {intencion}")
        except Exception as e:
            self.logger.warning(f"❌ Error detectando intención: {e}")
            intencion = "continuar"  # fallback seguro


        
        nuevo_estado = state.copy()
        campos = ["incident_user_name", "incident_last_name", "incident_store_name", "incident_department"]
        for campo in campos:
            print(f"👹campo1: {campo} - {nuevo_estado.get(campo, 'No especificado')}")
        nuevo_estado["last_activity"] = datetime.now()
        datos_extraidos = self._llm_extraccion(datos_actuales, mensaje_usuario)
        # ⚠️ Si el extractor devuelve un Command, lo devolvemos directamente
        if isinstance(datos_extraidos, Command):
            return datos_extraidos


        # Intentos acumulados si no se identificó la tienda
        intento_tienda = state.get("intento_tienda", 0)
        tienda_llm = datos_extraidos.get("tienda")

        tienda_identificada = tienda_llm in self.tiendas if tienda_llm else False

        if tienda_llm and not tienda_identificada:
            intento_tienda += 1
            if intento_tienda >= 3:
                return Command(update={
                    "incident_store_name": tienda_llm,
                    "tienda_identificada": False,
                    "incident_store_name_temp": None,
                    "intento_tienda": intento_tienda,
                    "messages": [AIMessage(content=f"No he encontrado la tienda '{tienda_llm}' en la base de datos, pero la he guardado igualmente.")],
                    "current_node": "identificar_incidencia",
                    "awaiting_user_input": True,
                    "authenticated": False
                })
            else:
                return Command(update={
                    "incident_store_name_temp": tienda_llm,
                    "intento_tienda": intento_tienda,
                    "messages": [AIMessage(content="No he podido identificar tu tienda. ¿Podrías escribir el nombre exacto, por ejemplo: Hipermercado Bilbondo?")],
                    "current_node": "identificar_incidencia",
                    "awaiting_user_input": True,
                    "authenticated": False
                })




        print(f"👹datos_extraidos: {datos_extraidos}")
        # 3. Detectar cambios en el estado (si hay alguna
        resultado_confirmacion = self._detectar_cambios(state, datos_extraidos)
        print(f"👹resultado_confirmacion: {resultado_confirmacion}")



        if isinstance(resultado_confirmacion, Command):
            return resultado_confirmacion  # Salimos del nodo pidiendo confirmación
        
        if any(valor is not None for valor in datos_extraidos.values()):
            
            return self._actualizar_estado(nuevo_estado, datos_extraidos)
            
        if intencion == "modificar":
            # 4. Actualizar estado con los datos extraídos
            if datos_extraidos.get("nombre"): nuevo_estado["incident_user_name"] = datos_extraidos["nombre"]
            if datos_extraidos.get("apellido"): nuevo_estado["incident_last_name"] = datos_extraidos["apellido"]
            if datos_extraidos.get("tienda"): nuevo_estado["incident_store_name"] = datos_extraidos["tienda"]
            if datos_extraidos.get("seccion"): nuevo_estado["incident_department"] = datos_extraidos["seccion"]
            resumen = (
                    f"✅ He actualizado tus datos:\n\n"
                    f"👤 {nuevo_estado.get('incident_user_name', 'No especificado')} {nuevo_estado.get('incident_last_name', '')}\n"
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
            print(f"👹intencion: {intencion}")
            campos = ["incident_user_name", "incident_last_name", "incident_store_name", "incident_department"]
            for campo in campos:
                print(f"👹campo: {campo} - {nuevo_estado.get(campo, 'No especificado')}")
            if all(nuevo_estado.get(campo) for campo in campos):
                resumen = (
                    f"✅ Te he identificado:\n\n"
                    f"👤 {nuevo_estado['incident_user_name']} {nuevo_estado['incident_last_name']}\n"
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
                if not nuevo_estado.get("incident_user_name"): faltan.append("tu nombre")
                if not nuevo_estado.get("incident_last_name"): faltan.append("tu apellido")
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
    
    def _llm_extraccion(self, datos_actuales: Dict[str, Optional[str]], 
                        mensaje_usuario: str, 
                        intentos_identificacion: int = 0,
                        intento_tienda: int =0) -> dict:
        
        class datos_salida(BaseModel):
            nombre: Optional[str] = Field(description="Nombre de la persona")
            apellido: Optional[str] = Field(description="Apellido de la persona")
            tienda: Optional[str] = Field(description="Tienda donde se produce la incidencia")
            tienda_tentativa: Optional[str] = Field(description="Tienda proporcinada por el usuario y que no se encuentra en la lista de tiendas")
            seccion: Optional[str] = Field(description="Departamento donde se produce la incidencia")
            respuesta: Optional[str] = Field(description="Respuesta que hay que devolver al usuario")
            authenticated: bool = Field(description="Indica si tenemos los valores en los cuatro campos")
        
        
        parser = JsonOutputParser(pydantic_object=datos_salida)
        datos_actuales_text = "\n".join([f"- {k}: {v}" for k, v in datos_actuales.items()])
        
        system_prompt = f"""
        Eres un asistente de Eroski. Tu tarea es extraer hasta 4 campos del mensaje del usuario:

        - nombre
        - apellido
        - seccion (Carnicería, Pescadería, Panadería, Caja, etc.)
        - tienda (de esta lista: {', '.join(self.tiendas[:20])})

        Si has identificado una tienda pero no está en la lista, guarda este dato en el campo `tienda_tentativa`.
        Si tienes los 4 campos (nombre, apellido, sección y tienda), pon el valor `authenticated` a True
        
        === DATOS ACTUALES DEL USUARIO ===
        {datos_actuales_text}

        === PARÁMETROS DE CONTEXTO ===
        - intentos_identificacion: {intentos_identificacion}
        - intento_tienda: {intento_tienda}

        === INSTRUCCIONES DE EXTRACCIÓN ===
        - Solo actualiza un campo si el usuario lo menciona clara y directamente.
        - Si no lo menciona, déjalo como null.
        - No infieras. Por ejemplo, "problema con el TPV" no implica Caja.
        - Si el usuario menciona un dato distinto al que ya teníamos registrado, considera que quiere modificarlo y actualízalo.

        === INSTRUCCIONES PARA LA RESPUESTA AL USUARIO ===
        - Si has actualizado algún dato respecto a los datos actuales, infórmaselo de forma clara y amable.
            Ejemplo: "He actualizado tu sección a Panadería."
        - Si tienes los 4 campos (nombre, apellido, sección y tienda), da las gracias, muestra los datos identificados y di que pasas a recoger la incidencia.
        - También debes pasar a recoger la incidencia si la tienda no está en la lista, pero ya se ha proporcionado varias veces y la estamos aceptando igualmente.
            En ese caso, muestra los datos y continúa con: "Gracias, ya tengo tus datos. Vamos ahora con la incidencia."
        - Si faltan campos, pide que los proporcione.
        - Si la tienda identificada no está en la lista, indícaselo al usuario:
            - Si `intento_tienda` es 1 o 2 → Pide amablemente que vuelva a indicar la tienda.
            - Si `intento_tienda` es 3 → Guarda la tienda proporcionada como `tienda_tentativa` y avisa que no se encontró, pero se usará igualmente. En este pon en la variable ´tienda´  el valor de ´tienda_tentativa´
        - Si `tienda_tentativa` es igual a la tienda proporcionada por el usuario en este mensaje, y esta tienda **no está en la lista de tiendas válidas**, avísale educadamente que esa tienda no la encontrabas previamente.
        - Si `tienda_tentativa` no es nula, es distinta de la tienda proporcionada en este mensaje, **y la nueva tienda tampoco está en la lista de tiendas válidas**, dile que esa nueva tienda tampoco la encuentras.

        


        === FORMATO DE SALIDA ===
        Devuelve un JSON con los campos: nombre, apellido, tienda, tienda_tentativa, seccion, respuesta, y authenticated.
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
            # Detectar errores de filtrado de contenido (Azure OpenAI)
            if hasattr(e, "args") and "content_filter" in str(e.args[0]).lower():
                mensaje = (
                    "Tu mensaje ha sido bloqueado por las políticas del sistema. "
                    "¿Podrías reformularlo con otras palabras, por favor?"
                )
            else:
                mensaje = "No he entendido tu mensaje. ¿Podrías repetirlo más claramente?"

            return self._respuesta_ai(mensaje)
            
        # Si `self.llm` devuelve texto plano JSON, conviértelo:
        return data
    
    def _actualizar_estado(self, estado: EroskiState, datos_extraidos: dict) -> Command:
        """Actualiza el estado con los datos extraídos con el LLM si algún campo estaba vacío y ahora puede rellenarse."""

        mapeo = {
            "incident_user_name": "nombre",
            "incident_last_name": "apellido",
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
            "incident_user_name": "nombre",
            "incident_last_name": "apellido",
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
            "incident_user_name": "nombre",
            "incident_last_name": "apellido",
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