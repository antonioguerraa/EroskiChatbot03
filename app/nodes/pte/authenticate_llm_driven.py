# =====================================================
# nodes/authenticate_llm_driven.py - Nodo de Autenticación LLM-Driven
# =====================================================
"""
Nodo de autenticación inteligente dirigido completamente por LLM.

FUNCIONALIDAD NUEVA:
1. LLM dirige toda la conversación desde el primer mensaje
2. Recopila datos de forma natural y eficiente
3. Maneja información múltiple en un solo intercambio
4. Busca en BD automáticamente cuando detecta email
5. Adaptación contextual inteligente
6. Fallback robusto en caso de errores
"""

from typing import Dict, Any, Optional, List, Union
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from datetime import datetime
import logging
import json
import re

from app.models.eroski_state import EroskiState
from app.nodes.base_node import BaseNode
from app.utils.old.eroski_database_auth import EroskiEmployeeDatabaseAuth
from app.utils.llm.providers import get_llm
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field


# =============================================================================
# MODELOS DE DATOS
# =============================================================================

class ConversationDecision(BaseModel):
    """Decisión del LLM sobre qué hacer en la conversación"""
    
    # Estado de la recopilación
    is_complete: bool = Field(description="Si tiene todos los datos necesarios")
    should_search_database: bool = Field(description="Si debe buscar en base de datos")
    wants_to_cancel: bool = Field(description="Si el usuario quiere cancelar")
    
    # Datos extraídos del mensaje actual
    extracted_data: Dict[str, Any] = Field(description="Datos extraídos del mensaje")
    
    # ✅ NUEVO FLAG PARA DETECCIÓN DE EMAIL
    email_detected: bool = Field(description="Si se ha detectado un email en el mensaje actual", default=False)
    

    # Próxima acción
    next_action: str = Field(description="Próxima acción: collect_data, search_db, complete, cancel, clarify")
    message_to_user: str = Field(description="Mensaje natural para el usuario")
    
    # Información de estado
    missing_fields: List[str] = Field(description="Campos que aún faltan", default=[])
    confidence_level: float = Field(description="Confianza en la extracción (0-1)", default=0.0)


# =============================================================================
# NODO PRINCIPAL LLM-DRIVEN
# =============================================================================

class LLMDrivenAuthenticateNode(BaseNode):
    """
    Nodo de autenticación completamente dirigido por LLM.
    
    CARACTERÍSTICAS:
    - Conversación natural desde el primer intercambio
    - Recopilación inteligente de múltiples datos por mensaje
    - Búsqueda automática en BD cuando detecta email
    - Sin etapas fijas - flujo adaptativo
    - Fallback robusto ante errores
    """
    
    def __init__(self):
        super().__init__("authenticate")
        self.max_attempts = 5  # Menos intentos porque es más eficiente
        self.db_auth = EroskiEmployeeDatabaseAuth()
        self.llm = get_llm()
        
        # Parser para decisiones LLM
        self.parser = JsonOutputParser(pydantic_object=ConversationDecision)
        
        # Sistema principal de conversación
        self.conversation_prompt = self._build_conversation_prompt()
        
        # Campos requeridos para completar autenticación
        self.required_fields = {
            "name": "Nombre completo del empleado",
            "email": "Email (no obligatorio que sea @eroski.es)",
            "store_name": "Nombre de la tienda donde trabaja",
            "section": "Sección específica donde ocurrió la incidencia"
        }
    
    def get_required_fields(self) -> List[str]:
        return ["messages"]
    
    def get_actor_description(self) -> str:
        return "Recopilo datos de empleados usando conversación natural dirigida por IA"
    
    async def execute(self, state: EroskiState) -> Command:
        """
        Ejecutar autenticación LLM-driven.
        
        Args:
            state: Estado actual del workflow
            
        Returns:
            Command con la siguiente acción
        """
        
        self.logger.info(f"🧪 Estado inicial - auth_conversation_started: {state.get('auth_conversation_started')}")

        """Ejecutar autenticación LLM-driven - CON DEBUG COMPLETO"""

        self.logger.info("🏅"*50)
        self.logger.info(f"🌄JGL entrando en {self.__class__.__name__}")
        
        # ✅ DEBUG: Ver estado de entrada
        self.logger.info(f"📊 Estado de entrada: session_id={state.get('session_id')}")
        self.logger.info(f"📊 Mensajes: {len(state.get('messages', []))}")
        self.logger.info(f"📊 Auth data collected: {state.get('auth_data_collected', {})}")
        
        collected_data = state.get("auth_data_collected", {})
        filled_fields = [k for k in self.required_fields if collected_data.get(k)]
        missing_fields = [k for k in self.required_fields if not collected_data.get(k)]
        self.logger.info(f"🟢 Campos rellenados: {filled_fields}")
        self.logger.info(f"🔴 Campos faltantes: {missing_fields}")

        try:
            self.logger.info("🤖 Iniciando autenticación LLM-driven")
            
            # 1. Verificar si ya está completo
            if self._is_authentication_complete(state):
                return self._proceed_to_next_step(state)
            
            self.logger.info(f"🌄primera visita {self._is_first_visit(state)}")
            # 2. Primera visita - mensaje inteligente de bienvenida
            if self._is_first_visit(state):

                self.logger.info(f"🌄Entra primera visita")
                try:
                    self.logger.info("🤖 Analizando primer mensaje con LLM...")
                    decision = await self._get_llm_decision(state)
                    
                    # Si el LLM extrajo algún dato, procesarlo
                    if decision.extracted_data and any(decision.extracted_data.values()):
                        self.logger.info(f"🚀 LLM extrajo datos del primer mensaje: {decision.extracted_data}")
                        return await self._execute_llm_decision(state, decision)
                    else:
                        self.logger.info("📋 LLM no extrajo datos, enviando bienvenida")
                        return await self._start_intelligent_conversation(state)
                        
                except Exception as e:
                    self.logger.warning(f"⚠️ Error analizando primer mensaje con LLM: {e}")
                    return await self._start_intelligent_conversation(state)

            # 3. Continuar conversación dirigida por LLM
            result = await self._continue_llm_conversation(state)
            self.logger.info("🔍 === RESULTADO DEL NODO ===")
            if hasattr(result, 'update'):
                update_data = result.update
                self.logger.info(f"🔍 authentication_stage: {update_data.get('authentication_stage')}")
                self.logger.info(f"🔍 datos_usuario_completos: {update_data.get('datos_usuario_completos')}")
                self.logger.info(f"🔍 ready_for_classification: {update_data.get('ready_for_classification')}")
                self.logger.info(f"🔍 awaiting_user_input: {update_data.get('awaiting_user_input')}")
                self.logger.info(f"🔍 employee_name: {update_data.get('employee_name')}")
                self.logger.info(f"🔍 incident_store_name: {update_data.get('incident_store_name')}")
                self.logger.info(f"🔍 incident_section: {update_data.get('incident_section')}")
            self.logger.info("🔍 === FIN RESULTADO ===")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Error en autenticación LLM: {e}")
            return await self._handle_llm_error(state, str(e))
    
    # =========================================================================
    # LÓGICA PRINCIPAL DE CONVERSACIÓN
    # =========================================================================
    
    async def _start_intelligent_conversation(self, state: EroskiState) -> Command:
        """Iniciar conversación inteligente"""
        
        existing_messages = state.get("messages", [])
        self.logger.info(f"🌄JGL: _start_intelligent_conversation: {existing_messages}")    
        
        welcome_message = """¡Hola! 👋 Soy tu asistente de incidencias técnicas de Eroski.

Para ayudarte de la manera más eficiente, necesito conocer algunos datos:

🔹 **Tu nombre completo**
🔹 **Tu email** (no tiene que ser necesariamente @eroski.es)  
🔹 **Nombre de tu tienda** (ej: "Eroski Bilbao Centro")
🔹 **Sección donde ocurrió el problema** (ej: "Carnicería", "Caja", "Almacén")

Puedes darme **toda la información de una vez** o por partes, como prefieras. 😊

**Ejemplo:** *"Hola, soy María García, mi email es maria@eroski.es, trabajo en Eroski Madrid Centro en la sección de panadería"*

*(Escribe "cancelar" si cambias de opinión)*"""
        self.logger.info(f"🌄JGL: _start_intelligent_conversation: {state.get('messages', [])}")
        self.logger.info(f"🌄JGL: _start_intelligent_conversation: {[AIMessage(content=welcome_message)]}")
        return Command(update={
            "current_node": "authenticate",
            "messages": state.get("messages", []) + [AIMessage(content=welcome_message)],
            "attempts": state.get("attempts", 0) + 1,
            "auth_conversation_started": True,
            "awaiting_user_input": True,
            "auth_data_collected": state.get("auth_data_collected", {}),
            "last_activity": datetime.now()
        })
    
    async def _continue_llm_conversation(self, state: EroskiState) -> Command:
        """Continuar conversación dirigida por LLM"""
        
        try:
            # Obtener decisión del LLM
            decision = await self._get_llm_decision(state)
            
            # Ejecutar la acción decidida por el LLM
            return await self._execute_llm_decision(state, decision)
            
        except Exception as e:
            self.logger.error(f"❌ Error en conversación LLM: {e}")
            return await self._fallback_to_manual_mode(state)
    
    async def _get_llm_decision(self, state: EroskiState) -> ConversationDecision:
        """Obtener decisión inteligente del LLM"""

        # Preparar contexto completo
        context = self._build_conversation_context(state)

        # Formatear prompt
        formatted_prompt = self.conversation_prompt.format(**context)

        # Invocar LLM
        self.logger.debug("🤖 Solicitando decisión a LLM...")
        self.logger.debug(f"🤖 Prompt: {formatted_prompt[:200]}...")
        response = await self.llm.ainvoke(formatted_prompt)
        # ✅ LOGGING DE LA RESPUESTA DEL LLM
        self.logger.info(f"🤖 Respuesta LLM: {response.content}")

        try:
            raw_response = response.content
            self.logger.debug(f"📥 Respuesta cruda del LLM: {raw_response}")
            self.logger.debug(f"🧪 Tipo real de raw_response: {type(raw_response)}")

            # 🔧 Si viene como string, limpiar y parsear
            if isinstance(raw_response, str):
                raw_response = raw_response.strip()
                if raw_response.startswith("```json"):
                    raw_response = raw_response.replace("```json", "").strip()
                if raw_response.startswith("```"):
                    raw_response = raw_response.replace("```", "").strip()
                if raw_response.endswith("```"):
                    raw_response = raw_response[:-3].strip()

                self.logger.debug(f"📥 JSON limpio para parser: ->{raw_response}<-")

                # Parsear con JsonOutputParser
                parsed = self.parser.parse(raw_response)

                # Verificar si es dict (por fallback interno del parser)
                if isinstance(parsed, dict):
                    decision = ConversationDecision(**parsed)
                else:
                    decision = parsed

            # ✅ Si ya viene como dict, construir el modelo directamente
            elif isinstance(raw_response, dict):
                self.logger.debug("📥 Dict detectado, creando modelo directamente")
                decision = ConversationDecision(**raw_response)

            else:
                raise ValueError("⚠️ Respuesta del LLM en formato inesperado")

            self.logger.info(f"📧 Email detectado: {decision.email_detected}")
            if decision.email_detected:
                self.logger.info(f"📧 Email extraído: {decision.extracted_data.get('email')}")

            self.logger.info(f"🧠 Datos extraídos por el LLM: {decision.extracted_data}")
            self.logger.info(f"🎯 LLM decidió: {decision.next_action}")
            return decision

        except Exception as parse_error:
            self.logger.warning(f"⚠️ Error parseando LLM, usando fallback: {parse_error}")
            return self._create_fallback_decision(state)

    async def _execute_llm_decision(self, state: EroskiState, decision: ConversationDecision) -> Command:
        """Ejecutar la decisión tomada por el LLM"""
        
        # Actualizar datos recopilados
        current_data = state.get("auth_data_collected", {})
        current_data.update(decision.extracted_data)
        # ✅ LOGGING PARA VER QUE DATOS TENEMOS
        self.logger.info(f"🧠 Datos antes de procesar: {current_data}")
        self.logger.info(f"🎯 Acción decidida: {decision.next_action}")
        self.logger.info(f"📧 Email detectado: {decision.email_detected}")
        base_update = {
            "auth_data_collected": current_data,
            "attempts": state.get("attempts", 0) + 1,
            "last_activity": datetime.now(),
            "messages": state.get("messages", []) + [AIMessage(content=decision.message_to_user)]
        }
        # ✅ VERIFICAR SI TENEMOS TODOS LOS DATOS NECESARIOS ANTES DE PROCESAR
        has_all_required_data = all(current_data.get(field) for field in ["name", "email", "store_name", "section"])
        self.logger.info(f"🔍 ¿Tiene todos los datos requeridos? {has_all_required_data}")
        self.logger.info(f"🔍 Datos: name={bool(current_data.get('name'))}, email={bool(current_data.get('email'))}, store={bool(current_data.get('store_name'))}, section={bool(current_data.get('section'))}")
        # Ejecutar acción específica
        if decision.wants_to_cancel:
            return await self._handle_cancellation(state, decision)
            
        # ✅ NUEVA LÓGICA: Verificar flag de email
        elif decision.email_detected and decision.extracted_data.get("email"):
            self.logger.info(f"🔍 LLM detectó email: {decision.extracted_data.get('email')}")
            return await self._search_database_and_continue(state, decision, base_update)

        elif decision.next_action == "search_db":
            return await self._search_database_and_continue(state, decision, base_update)
            
        elif decision.next_action == "complete":
                # LLM dice que está completo, verificar si realmente lo está
                if has_all_required_data:
                    return self._complete_authentication_immediately(state, current_data, base_update)
                else:
                    self.logger.warning("⚠️ LLM dice 'complete' pero faltan datos")
                    return self._continue_data_collection(state, decision, base_update)
            
        elif decision.next_action == "collect_data":
            return self._continue_data_collection(state, decision, base_update)
            
        else:  # clarify or unknown
            return self._request_clarification(state, decision, base_update)

    def _complete_authentication_immediately(self, state: EroskiState, current_data: Dict, base_update: Dict) -> Command:
        """Completar autenticación inmediatamente cuando tenemos todos los datos"""
        
        self.logger.info("🚀 === COMPLETANDO AUTENTICACIÓN INMEDIATAMENTE ===")
        self.logger.info(f"📊 Datos completos: {current_data}")
        
        # Mensaje de confirmación
        confirmation_message = f"""✅ **1. ¡Información recopilada correctamente!**

    👤 **Empleado:** {current_data.get('name')}
    📧 **Email:** {current_data.get('email')}
    🏪 **Tienda:** {current_data.get('store_name')}
    📍 **Sección:** {current_data.get('section')}
    """
        
        # ✅ CONFIGURAR TODOS LOS CAMPOS REQUERIDOS POR EL ROUTER
        complete_update = {
            **base_update,  # Incluir datos base
            
            # ✅ CAMPOS CRÍTICOS PARA EL ROUTER
            "authentication_stage": "completed",
            "datos_usuario_completos": True,
            "ready_for_classification": True,
            "awaiting_user_input": False,  # ✅ CRÍTICO - NO esperar input
            
            # ✅ CAMPOS DE EMPLEADO REQUERIDOS
            "employee_name": current_data.get('name'),
            "incident_store_name": current_data.get('store_name'),
            "incident_section": current_data.get('section'),
            "incident_email": current_data.get('email'),
            
            # ✅ CAMPOS ADICIONALES
            "authenticated": True,
            "found_in_database": False,  # Asumimos manual por defecto
            "current_node": "authenticate",
            
            # ✅ SOBRESCRIBIR MENSAJE
            "messages": state.get("messages", []) + [AIMessage(content=confirmation_message)]
        }
        
        # ✅ LOGGING PARA VERIFICAR QUE SE CONFIGURAN TODOS LOS CAMPOS
        self.logger.info("✅ === CONFIGURANDO ESTADO COMPLETO ===")
        self.logger.info(f"✅ authentication_stage: {complete_update['authentication_stage']}")
        self.logger.info(f"✅ datos_usuario_completos: {complete_update['datos_usuario_completos']}")
        self.logger.info(f"✅ ready_for_classification: {complete_update['ready_for_classification']}")
        self.logger.info(f"✅ awaiting_user_input: {complete_update['awaiting_user_input']}")
        self.logger.info(f"✅ employee_name: {complete_update['employee_name']}")
        self.logger.info(f"✅ incident_store_name: {complete_update['incident_store_name']}")
        self.logger.info(f"✅ incident_section: {complete_update['incident_section']}")
        self.logger.info("✅ === FIN CONFIGURACIÓN ESTADO ===")
        self.logger.info('🌄JGL Lo enviamos a classify')
        return Command(update=complete_update, goto="classify")


    # =========================================================================
    # ACCIONES ESPECÍFICAS
    # =========================================================================
    async def _search_database_and_continue(self, state: EroskiState, decision: ConversationDecision, base_update: Dict) -> Command:
        """Buscar en BD y continuar - MANEJO ROBUSTO DE NO ENCONTRADOS"""
        
        email = decision.extracted_data.get("email")
        self.logger.info(f"🔍 Ejecutando búsqueda en BD para: {email}")
        
        # 1. BUSCAR EN BASE DE DATOS
        db_result = await self._search_employee_database(email)
        
        if db_result.get("found"):
            # ✅ CASO 1: USUARIO ENCONTRADO EN BD
            return await self._handle_user_found_in_db(state, decision, base_update, db_result)
        
        elif db_result.get("is_error"):
            # ✅ CASO 2: ERROR TÉCNICO EN BD
            return await self._handle_database_technical_error(state, decision, base_update, db_result)
        
        else:
            # ✅ CASO 3: EMAIL NO REGISTRADO (CASO NORMAL)
            return await self._handle_email_not_registered(state, decision, base_update, db_result)

    async def _handle_database_technical_error(self, state: EroskiState, decision: ConversationDecision, base_update: Dict, db_result: Dict) -> Command:
        """Manejar error técnico de base de datos"""
        
        error = db_result.get("error", "Error desconocido")
        email = db_result.get("email")
        
        self.logger.error(f"❌ Error técnico en BD para {email}: {error}")
        
        # ✅ INTENTAR COMPLETAR CON DATOS MANUALES SI LOS TENEMOS
        current_data = base_update["auth_data_collected"]
        has_all_data = all(current_data.get(field) for field in ["name", "email", "store_name", "section"])
        
        if has_all_data:
            self.logger.info("✅ Error en BD pero tenemos todos los datos, completando manualmente")
            
            error_message = f"""Ha ocurrido un problema técnico al verificar tu email, pero ya tengo toda tu información necesaria. 👍

    **Datos registrados:**
    👤 **Empleado:** {current_data.get('name')}
    📧 **Email:** {current_data.get('email')}
    🏪 **Tienda:** {current_data.get('store_name')}
    📍 **Sección:** {current_data.get('section')}

    ¡Continuemos! **¿Qué problema técnico estás experimentando?** 🔧"""
            
            # Completar autenticación a pesar del error
            base_update.update({
                "authentication_stage": "completed",
                "datos_usuario_completos": True,
                "ready_for_classification": True,
                "awaiting_user_input": False,  # ✅ CONTINUAR
                "employee_name": current_data.get('name'),
                "incident_store_name": current_data.get('store_name'),
                "incident_section": current_data.get('section'),
                "incident_email": current_data.get('email'),
                "found_in_database": False,
                "database_error": error,
                "authenticated": True,
                "messages": state.get("messages", []) + [AIMessage(content=error_message)]
            })
            
            return Command(update=base_update)
        
        else:
            # Error y no tenemos datos suficientes
            error_message = f"""Ha ocurrido un error técnico al verificar tu email. 😔

    Para continuar, necesito que me proporciones manualmente:
    🔹 **Tu nombre completo**
    🔹 **Nombre de tu tienda**
    🔹 **Sección donde trabajas**

    **Ejemplo:** "Soy Juan García, trabajo en Eroski Bilbao Centro en carnicería" """
            
            base_update.update({
                "awaiting_user_input": True,
                "database_error": error,
                "messages": state.get("messages", []) + [AIMessage(content=error_message)]
            })
            
            return Command(update=base_update)

    async def _handle_email_not_registered(self, state: EroskiState, decision: ConversationDecision, base_update: Dict, db_result: Dict) -> Command:
        """Manejar email no registrado en BD (CASO NORMAL)"""
        
        email = db_result.get("email")
        self.logger.info(f"📄 Email no registrado en BD: {email} - Continuando con datos manuales")
        
        # ✅ VERIFICAR SI TENEMOS TODOS LOS DATOS NECESARIOS
        current_data = base_update["auth_data_collected"]
        
        has_name = bool(current_data.get("name"))
        has_store = bool(current_data.get("store_name"))
        has_section = bool(current_data.get("section"))
        has_email = bool(current_data.get("email"))
        
        self.logger.info(f"📋 Verificando datos - Nombre: {has_name}, Tienda: {has_store}, Sección: {has_section}, Email: {has_email}")
        
        if has_name and has_store and has_section and has_email:
            # ✅ TENEMOS TODOS LOS DATOS - COMPLETAR AUTENTICACIÓN
            self.logger.info("✅ Todos los datos disponibles, completando autenticación sin BD")
            
            confirmation_message = f"""✅ **2. ¡Información recopilada correctamente!**

    Tu email no está registrado en nuestra base de datos, pero no hay problema. He registrado tus datos manualmente:

    👤 **Empleado:** {current_data.get('name')}
    📧 **Email:** {current_data.get('email')}
    🏪 **Tienda:** {current_data.get('store_name')}
    📍 **Sección:** {current_data.get('section')}

    """
            
            # Configurar estado completo
            base_update.update({
                "authentication_stage": "completed",
                "datos_usuario_completos": True,
                "ready_for_classification": True,
                "awaiting_user_input": False,  # ✅ CRÍTICO
                "employee_name": current_data.get('name'),
                "incident_store_name": current_data.get('store_name'),
                "incident_section": current_data.get('section'),
                "incident_email": current_data.get('email'),
                "found_in_database": False,
                "authenticated": True,
                "manual_registration": True,  # ✅ Indicar que fue registro manual
                "messages": state.get("messages", []) + [AIMessage(content=confirmation_message)]
            })
            self.logger.info('🌄JGL Lo enviamos a classify')
            return Command(update=base_update, goto='classify')
        
        else:
            # ✅ FALTAN DATOS - PEDIRLOS ESPECÍFICAMENTE
            missing_fields = []
            if not has_name:
                missing_fields.append("nombre completo")
            if not has_store:
                missing_fields.append("nombre de tu tienda")
            if not has_section:
                missing_fields.append("sección donde trabajas")
            
            return self._request_missing_fields_for_manual_registration(state, current_data, missing_fields, base_update, email)

    def _request_missing_fields_for_manual_registration(self, state: EroskiState, current_data: Dict, missing_fields: List[str], base_update: Dict, email: str) -> Command:
        """Pedir campos faltantes para registro manual"""
        
        # Mostrar lo que ya tenemos
        confirmed_parts = []
        if current_data.get("name"):
            confirmed_parts.append(f"👤 **Nombre:** {current_data['name']}")
        if current_data.get("email"):
            confirmed_parts.append(f"📧 **Email:** {current_data['email']}")
        if current_data.get("store_name"):
            confirmed_parts.append(f"🏪 **Tienda:** {current_data['store_name']}")
        if current_data.get("section"):
            confirmed_parts.append(f"📍 **Sección:** {current_data['section']}")
        
        confirmed_text = "\n".join(confirmed_parts) if confirmed_parts else ""
        
        # Construir mensaje
        if len(missing_fields) == 1:
            missing_text = f"tu **{missing_fields[0]}**"
        else:
            missing_text = f"tu **{' y '.join(missing_fields)}**"
        
        if confirmed_text:
            message = f"""Tu email `{email}` no está en nuestra base de datos, pero puedo registrarte manualmente. 📝

    **Datos que ya tengo:**
    {confirmed_text}

    Para completar tu registro, necesito {missing_text}.

    **Ejemplo:** "Trabajo en Eroski Madrid Centro en la sección de carnicería" """
        else:
            message = f"""Tu email `{email}` no está en nuestra base de datos, pero puedo ayudarte registrándote manualmente. 📝

    Necesito que me proporciones {missing_text}.

    **Ejemplo:** "Soy María García, trabajo en Eroski Madrid Centro en panadería" """
        
        base_update.update({
            "awaiting_user_input": True,
            "found_in_database": False,
            "pending_manual_registration": True,
            "registration_email": email,
            "missing_fields": missing_fields,
            "messages": state.get("messages", []) + [AIMessage(content=message)]
        })
        
        return Command(update=base_update)


    async def _handle_user_found_in_db(self, state: EroskiState, decision: ConversationDecision, base_update: Dict, db_result: Dict) -> Command:
        """Manejar usuario encontrado en BD"""
        
        employee = db_result["employee"]
        self.logger.info(f"✅ Usuario encontrado en BD: {employee.get('name')}")
        
        success_message = f"""✅ **¡Perfecto {employee.get('name', 'usuario')}!** Te he encontrado en el sistema.

    **Datos confirmados:**
    👤 **Nombre:** {employee.get('name')}
    🏪 **Tienda:** {employee.get('store_name')}
    📧 **Email:** {decision.extracted_data.get('email')}

    Ahora cuéntame: **¿qué problema técnico necesitas reportar?** 🔧"""
        
        # Configurar estado completo
        base_update.update({
            "authentication_stage": "completed",
            "datos_usuario_completos": True,
            "ready_for_classification": True,
            "awaiting_user_input": False,  # ✅ CRÍTICO
            "employee_name": employee.get('name'),
            "incident_store_name": employee.get('store_name'),
            "incident_section": decision.extracted_data.get("section", "Por especificar"),
            "incident_email": decision.extracted_data.get('email'),
            "found_in_database": True,
            "employee_data": employee,
            "authenticated": True,
            "messages": state.get("messages", []) + [AIMessage(content=success_message)]
        })
        self.logger.info('🌄JGL Lo enviamos a classify')
        return Command(update=base_update, goto = 'classify')
    def _complete_authentication_with_manual_data(self, state: EroskiState, current_data: Dict, base_update: Dict) -> Command:
        """Completar autenticación con datos manuales - VERSIÓN CORREGIDA"""
        
        confirmation_message = f"""✅ **3. ¡Información recopilada correctamente!**

    👤 **Empleado:** {current_data.get('name')}
    📧 **Email:** {current_data.get('email')}
    🏪 **Tienda:** {current_data.get('store_name')}
    📍 **Sección:** {current_data.get('section')}
"""
        
        # ✅ ASEGURAR QUE TODOS LOS CAMPOS REQUERIDOS ESTÉN CONFIGURADOS
        base_update.update({
            # Campos para el router
            "authentication_stage": "completed",           # ✅ OBLIGATORIO
            "datos_usuario_completos": True,               # ✅ OBLIGATORIO
            "ready_for_classification": True,              # ✅ OBLIGATORIO
            "awaiting_user_input": False,                  # ✅ CRÍTICO - NO esperar input
            
            # Campos de empleado requeridos por el router
            "employee_name": current_data.get('name'),     # ✅ OBLIGATORIO
            "incident_store_name": current_data.get('store_name'),  # ✅ OBLIGATORIO
            "incident_section": current_data.get('section'),       # ✅ OBLIGATORIO
            "incident_email": current_data.get('email'),
            
            # Otros campos
            "authenticated": True,
            "found_in_database": False,
            "current_node": "authenticate",
            "last_activity": datetime.now(),
            "messages": state.get("messages", []) + [AIMessage(content=confirmation_message)]
        })
        
        # ✅ LOGGING PARA VERIFICAR
        self.logger.info("✅ === COMPLETANDO AUTENTICACIÓN MANUAL ===")
        self.logger.info(f"✅ authentication_stage: {base_update['authentication_stage']}")
        self.logger.info(f"✅ datos_usuario_completos: {base_update['datos_usuario_completos']}")
        self.logger.info(f"✅ ready_for_classification: {base_update['ready_for_classification']}")
        self.logger.info(f"✅ awaiting_user_input: {base_update['awaiting_user_input']}")
        self.logger.info(f"✅ employee_name: {base_update['employee_name']}")
        self.logger.info(f"✅ incident_store_name: {base_update['incident_store_name']}")
        self.logger.info(f"✅ incident_section: {base_update['incident_section']}")
        
        self.logger.info('🌄JGL Lo enviamos a classify')
        return Command(update=base_update, goto="classify" )


    def _request_missing_fields_intelligently(self, state: EroskiState, current_data: Dict, missing_fields: List[str], base_update: Dict) -> Command:
        """Pedir solo los campos que faltan de forma inteligente"""
        
        # ✅ CONSTRUIR MENSAJE PERSONALIZADO SEGÚN LO QUE YA TENEMOS
        
        # Mostrar lo que ya tenemos
        confirmed_parts = []
        if current_data.get("name"):
            confirmed_parts.append(f"👤 **Nombre:** {current_data['name']}")
        if current_data.get("email"):
            confirmed_parts.append(f"📧 **Email:** {current_data['email']}")
        if current_data.get("store_name"):
            confirmed_parts.append(f"🏪 **Tienda:** {current_data['store_name']}")
        if current_data.get("section"):
            confirmed_parts.append(f"📍 **Sección:** {current_data['section']}")
        
        confirmed_text = "\n".join(confirmed_parts) if confirmed_parts else ""
        
        # ✅ PEDIR SOLO LO QUE FALTA
        if len(missing_fields) == 1:
            missing_text = f"tu **{missing_fields[0]}**"
        elif len(missing_fields) == 2:
            missing_text = f"tu **{missing_fields[0]}** y **{missing_fields[1]}**"
        else:
            missing_text = f"tu **{', '.join(missing_fields[:-1])}** y **{missing_fields[-1]}**"
        
        # Construir mensaje
        if confirmed_text:
            message = f"""Perfecto, ya tengo algunos datos:

    {confirmed_text}

    Para completar tu información, necesito que me proporciones {missing_text}.

    **Ejemplo:** "Trabajo en Eroski Madrid Centro en la sección de carnicería" """
        else:
            message = f"""Tu email no está en nuestra base de datos, pero no hay problema. 👍

    Para continuar, necesito que me proporciones {missing_text}.

    **Ejemplo:** "Soy María García, trabajo en Eroski Madrid Centro en panadería" """
        
        base_update.update({
            "awaiting_user_input": True,  # ✅ Esperar más información específica
            "found_in_database": False,
            "missing_fields": missing_fields,  # Guardar qué campos faltan
            "messages": state.get("messages", []) + [AIMessage(content=message)]
        })
        
        return Command(update=base_update)


    def _handle_database_error(self, state: EroskiState, base_update: Dict, error: str) -> Command:
        """Manejar error de base de datos de forma inteligente"""
        
        current_data = base_update["auth_data_collected"]
        
        # Verificar qué campos faltan aún con el error
        missing_fields = []
        if not current_data.get("name"):
            missing_fields.append("nombre completo")
        if not current_data.get("store_name"):
            missing_fields.append("nombre de tu tienda")
        if not current_data.get("section"):
            missing_fields.append("sección donde trabajas")
        
        if not missing_fields:
            # Tenemos todo, continuar a pesar del error
            error_message = """Ha habido un problema técnico al verificar tu email, pero ya tengo toda tu información necesaria. 👍

    ¡Continuemos! **¿Qué problema técnico estás experimentando?** 🔧"""
            
            base_update.update({
                "awaiting_user_input": False,  # Continuar
                "authentication_stage": "completed",
                "datos_usuario_completos": True,
                "database_error": error
            })
        else:
            # Faltan campos, pedirlos
            missing_text = ", ".join(missing_fields)
            error_message = f"""Ha ocurrido un error técnico al verificar tu email. 😔

    No te preocupes, puedo ayudarte igualmente. Necesito que me proporciones: **{missing_text}**.

    **Ejemplo:** "Soy Juan García, trabajo en Eroski Bilbao Centro en carnicería" """
            
            base_update.update({
                "awaiting_user_input": True,
                "database_error": error
            })
        
        base_update["messages"] = state.get("messages", []) + [AIMessage(content=error_message)]
        
        return Command(update=base_update)



    def _complete_authentication(self, state: EroskiState, decision: ConversationDecision, base_update: Dict) -> Command:
        """Completar proceso de autenticación"""
        
        collected_data = base_update["auth_data_collected"]
        
        # Mensaje de confirmación final


        
        confirmation_message = f"""✅ **4. ¡Información recopilada correctamente!**

👤 **Empleado:** {collected_data.get('name')}
📧 **Email:** {collected_data.get('email')}
🏪 **Tienda:** {collected_data.get('store_name')}
📍 **Sección:** {collected_data.get('section')}

🔧 **Ahora cuéntame:** ¿Qué problema técnico estás experimentando?

*(Describe el problema con el mayor detalle posible)*"""
        
        # Preparar datos finales
        final_update = {
            **base_update,
            "authentication_stage": "completed",
            "datos_usuario_completos": True,
            "employee_email": collected_data.get("email"),
            "employee_name": collected_data.get("name"),
            "incident_store_name": collected_data.get("store_name"),
            "incident_section": collected_data.get("section"),
            "ready_for_classification": True,
            "messages": state.get("messages", []) + [AIMessage(content=confirmation_message)]
        }
        
        # Si está en BD, agregar datos adicionales
        if collected_data.get("found_in_database"):
            final_update.update({
                "employee_id": collected_data.get("employee_id"),
                "store_id": collected_data.get("store_id"),
                "department": collected_data.get("department")
            })
        
        self.logger.info(f"✅ Autenticación completada para: {collected_data.get('name')}")
        return Command(update=final_update)
    
    def _continue_data_collection(self, state: EroskiState, decision: ConversationDecision, base_update: Dict) -> Command:
        """Continuar recopilando datos"""
        
        base_update["awaiting_user_input"] = True
        return Command(update=base_update)
    
    async def _handle_cancellation(self, state: EroskiState, decision: ConversationDecision) -> Command:
        """Manejar solicitud de cancelación"""
        
        cancellation_message = """🤔 Entiendo que quieres cancelar.

¿Estás seguro? Si confirmas, cerraré esta conversación.

**Responde:**
• **"Sí"** para cancelar definitivamente
• **"No"** para continuar con tu consulta 😊"""
        
        return Command(update={
            "awaiting_cancellation_confirmation": True,
            "messages": state.get("messages", []) + [AIMessage(content=cancellation_message)],
            "awaiting_user_input": True,
            "last_activity": datetime.now()
        })
    
    def _request_clarification(self, state: EroskiState, decision: ConversationDecision, base_update: Dict) -> Command:
        """Solicitar clarificación al usuario"""
        
        base_update["awaiting_user_input"] = True
        return Command(update=base_update)
    
    # =========================================================================
    # FUNCIONES AUXILIARES
    # =========================================================================

    def _extract_user_data(message: str) -> Dict[str, Any]:
        """Extraer datos del usuario del mensaje (versión simplificada)"""
        import re
        
        data = {}
        message_lower = message.lower()
        
        # Buscar email
        email_match = re.search(r'([a-zA-Z0-9._%+-]+@eroski\.es)', message)
        if email_match:
            data["email"] = email_match.group(1)
        
        # Buscar nombre (patrón simple)
        if "soy" in message_lower:
            name_match = re.search(r'soy\s+([a-záéíóúñ\s]+)', message_lower)
            if name_match:
                data["name"] = name_match.group(1).strip().title()
        
        # Buscar tienda
        if "eroski" in message_lower and ("centro" in message_lower or "tienda" in message_lower or "madrid" in message_lower):
            # Buscar patrones como "Eroski Madrid Centro"
            store_match = re.search(r'eroski\s+([a-záéíóúñ\s]+)', message_lower)
            if store_match:
                data["store_name"] = f"Eroski {store_match.group(1).strip().title()}"
        
        # Buscar sección
        sections = ["carnicería", "pescadería", "frutería", "panadería", "charcutería", "caja", "reposición", "seguridad", "administración", "it", "informática"]
        for section in sections:
            if section in message_lower:
                data["section"] = section.capitalize()
                break
        
        return data

    def _check_missing_fields(auth_data: Dict[str, Any]) -> list:
        """Verificar qué campos faltan"""
        required_fields = ["email", "name", "store_name", "section"]
        missing = []
        
        for field in required_fields:
            if not auth_data.get(field):
                missing.append(field)
        
        return missing

    def _generate_data_request_message(missing_fields: list, current_data: Dict[str, Any]) -> str:
        """Generar mensaje solicitando datos faltantes"""
        
        # Confirmar datos ya recibidos
        confirmation_parts = []
        if current_data.get("name"):
            confirmation_parts.append(f"👤 Nombre: {current_data['name']}")
        if current_data.get("email"):
            confirmation_parts.append(f"📧 Email: {current_data['email']}")
        if current_data.get("store_name"):
            confirmation_parts.append(f"🏪 Tienda: {current_data['store_name']}")
        if current_data.get("section"):
            confirmation_parts.append(f"🏢 Sección: {current_data['section']}")
        
        # Solicitar datos faltantes
        request_parts = []
        if "name" in missing_fields:
            request_parts.append("👤 Tu nombre completo")
        if "email" in missing_fields:
            request_parts.append("📧 Tu email corporativo (@eroski.es)")
        if "store_name" in missing_fields:
            request_parts.append("🏪 Tu tienda")
        if "section" in missing_fields:
            request_parts.append("🏢 Tu sección/departamento")
        
        message = "Perfecto, he registrado:\n\n"
        if confirmation_parts:
            message += "\n".join(confirmation_parts)
        
        message += "\n\nPara completar tu identificación, necesito:\n\n"
        message += "\n".join(request_parts)
        
        return message

    def _simulate_employee_lookup(auth_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simular búsqueda en base de datos (reemplazar con función real)"""
        
        # Datos simulados basados en la información proporcionada
        return {
            "id": "EMP001",
            "name": auth_data.get("name", "Usuario Temporal"),
            "email": auth_data.get("email", "temp@eroski.es"),
            "store_id": "STORE001",
            "store_name": auth_data.get("store_name", "Eroski Temporal"),
            "section": auth_data.get("section", "General"),
            "department": auth_data.get("section", "General"),
            "level": 2
        }

    def authenticate_employee_node():
        """Función wrapper para compatibilidad con importaciones anteriores"""
        return llm_driven_authenticate_node

    def _build_conversation_context(self, state: EroskiState) -> Dict[str, str]:
        """Construir contexto completo para el LLM"""
        
        # Obtener último mensaje del usuario
        user_message = self._get_last_user_message(state)
        
        # Obtener datos ya recopilados
        collected_data = state.get("auth_data_collected", {})
        
        # Construir historial de conversación
        conversation_history = self._get_conversation_summary(state)
        
        # Determinar qué campos faltan
        missing_fields = self._get_missing_fields(collected_data)
        
        return {
            "user_message": user_message,
            "collected_data": json.dumps(collected_data, indent=2, ensure_ascii=False),
            "conversation_history": conversation_history,
            "missing_fields": ", ".join(missing_fields),
            "required_fields_desc": json.dumps(self.required_fields, indent=2, ensure_ascii=False),
            "attempt_number": state.get("attempts", 0)
        }
    
    def _get_conversation_summary(self, state: EroskiState) -> str:
        """Obtener resumen de la conversación"""
        
        messages = state.get("messages", [])
        if len(messages) <= 2:
            return "Conversación recién iniciada"
        
        # Obtener últimos 3 intercambios
        recent_messages = messages[-6:]  # 3 intercambios = 6 mensajes
        
        summary_parts = []
        for i, msg in enumerate(recent_messages):
            if isinstance(msg, HumanMessage):
                summary_parts.append(f"Usuario: {msg.content[:100]}")
            elif isinstance(msg, AIMessage):
                summary_parts.append(f"Asistente: {msg.content[:100]}")
        
        return " | ".join(summary_parts)
    
    def _get_missing_fields(self, collected_data: Dict) -> List[str]:
        """Determinar qué campos aún faltan"""
        
        missing = []
        for field, description in self.required_fields.items():
            if not collected_data.get(field):
                missing.append(field)
        
        return missing
    
    def _has_all_required_data(self, collected_data: Dict) -> bool:
        """Verificar si tenemos todos los datos requeridos"""
        
        return all(collected_data.get(field) for field in self.required_fields.keys())
    
    def _is_authentication_complete(self, state: EroskiState) -> bool:
        """Verificar si la autenticación ya está completa"""
        
        return (
            state.get("authentication_stage") == "completed" and
            state.get("datos_usuario_completos") and
            state.get("employee_name") and
            state.get("incident_store_name") and
            state.get("incident_section")
        )
    
# ✅ CÓDIGO CORREGIDO
    def _is_first_visit(self, state: EroskiState) -> bool:
        """Verificar si es la primera visita al nodo - CORREGIDO"""
        
        messages = state.get("messages", [])
        ai_messages = [msg for msg in messages if isinstance(msg, AIMessage)]
        
        # Es primera visita SOLO si no hay mensajes del bot
        is_first = len(ai_messages) == 0
        
        self.logger.info(f"🔍 Primera visita? {is_first} - AI msgs: {len(ai_messages)}")
        return is_first
    
    def _proceed_to_next_step(self, state: EroskiState) -> Command:
        """Proceder al siguiente paso cuando la autenticación está completa"""
        
        self.logger.info("✅ Autenticación ya completa, procediendo a clasificación")
        self.logger.info('🌄JGL Lo enviamos a classify')

        return Command(update={
            "current_node": "authenticate",
            "last_activity": datetime.now()
            },
            goto="classify"
        )
    
    # =========================================================================
    # BÚSQUEDA EN BASE DE DATOS
    # =========================================================================
    
    async def _search_employee_database(self, email: str) -> Dict[str, Any]:
        """Buscar empleado en base de datos - MANEJO ROBUSTO"""
        
        try:
            self.logger.info(f"🔍 Buscando empleado en BD: {email}")
            
            # Asegurar que db_auth esté inicializado
            if not hasattr(self, 'db_auth') or self.db_auth is None:
                from app.utils.old.eroski_database_auth import EroskiEmployeeDatabaseAuth
                self.db_auth = EroskiEmployeeDatabaseAuth()
            
            # ✅ INTENTAR MÚLTIPLES MÉTODOS DE BÚSQUEDA
            employee_data = None
            
            # Método 1: validate_employee
            try:
                employee_data = await self.db_auth.validate_employee(email)
                if employee_data:
                    self.logger.info(f"✅ Empleado encontrado con validate_employee: {employee_data.get('name')}")
            except AttributeError:
                self.logger.debug("⚠️ Método validate_employee no disponible")
            except Exception as e:
                self.logger.debug(f"⚠️ Error en validate_employee: {e}")
            
            # Método 2: Si no se encontró, intentar otros métodos
            if not employee_data:
                try:
                    # Buscar por email usando repositorio directo
                    if hasattr(self.db_auth, 'user_repository'):
                        employee_data = await self.db_auth.user_repository.get_user_by_email(email)
                        if employee_data:
                            self.logger.info(f"✅ Empleado encontrado con user_repository: {employee_data.get('name')}")
                except Exception as e:
                    self.logger.debug(f"⚠️ Error en user_repository: {e}")
            
            # ✅ RESULTADO DE LA BÚSQUEDA
            if employee_data:
                self.logger.info(f"✅ Empleado encontrado en BD: {employee_data.get('name', 'Sin nombre')}")
                return {
                    "found": True,
                    "employee": employee_data,
                    "source": "database"
                }
            else:
                # ✅ NO ES UN ERROR - Es un caso normal
                self.logger.info(f"📄 Email {email} no está registrado en BD (caso normal)")
                return {
                    "found": False,
                    "reason": "Email no registrado en base de datos",
                    "email": email,
                    "is_error": False  # ✅ Indicar que NO es un error
                }
                
        except Exception as e:
            # ✅ ESTE SÍ ES UN ERROR TÉCNICO
            self.logger.error(f"❌ Error técnico en búsqueda BD: {e}")
            return {
                "found": False,
                "error": str(e),
                "email": email,
                "is_error": True  # ✅ Indicar que SÍ es un error
            }


    # =========================================================================
    # MANEJO DE ERRORES Y FALLBACKS
    # =========================================================================
    
    async def _handle_llm_error(self, state: EroskiState, error_message: str) -> Command:
        """Manejar errores del LLM"""
        
        self.logger.error(f"❌ Error LLM en autenticación: {error_message}")
        
        # Fallback a modo manual
        return await self._fallback_to_manual_mode(state)
    
    async def _fallback_to_manual_mode(self, state: EroskiState) -> Command:
        """Fallback a modo manual cuando LLM falla"""
        
        self.logger.warning("⚠️ Activando modo fallback manual")
        
        fallback_message = """Disculpa, he tenido un problema técnico momentáneo. 😅

Vamos paso a paso. ¿Podrías decirme tu **nombre completo**?"""
        
        return Command(update={
            "fallback_mode": True,
            "fallback_stage": "requesting_name",
            "messages": state.get("messages", []) + [AIMessage(content=fallback_message)],
            "awaiting_user_input": True,
            "attempts": state.get("attempts", 0) + 1,
            "last_activity": datetime.now()
        })
    
    def _create_fallback_decision(self, state: EroskiState) -> ConversationDecision:
        """Crear decisión de fallback cuando el parser falla"""
        
        # Análisis simple basado en palabras clave
        user_message = self._get_last_user_message(state).lower()
        
        # Detectar cancelación
        if any(word in user_message for word in ["cancelar", "salir", "no quiero", "adiós"]):
            return ConversationDecision(
                is_complete=False,
                wants_to_cancel=True,
                extracted_data={},
                next_action="cancel",
                message_to_user="Entiendo que quieres cancelar. ¿Estás seguro?"
            )
        
        # Detectar email
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', user_message)
        if email_match:
            return ConversationDecision(
                is_complete=False,
                should_search_database=True,
                extracted_data={"email": email_match.group()},
                next_action="search_db",
                message_to_user="Perfecto, déjame buscar tu información..."
            )
        
        # Por defecto, continuar recopilando
        return ConversationDecision(
            is_complete=False,
            extracted_data={},
            next_action="collect_data",
            message_to_user="Gracias por la información. ¿Podrías darme más detalles?"
        )
    
    def _get_last_user_message(self, state: EroskiState) -> str:
        """Obtener último mensaje del usuario"""
        
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return msg.content.strip()
        return ""
    
    # =========================================================================
    # PROMPT DEL LLM CONVERSACIONAL
    # =========================================================================
    
    def _build_conversation_prompt(self) -> PromptTemplate:
        """Construir prompt principal para el LLM conversacional"""
        
        return PromptTemplate(
            template="""Eres un asistente experto de Eroski especializado en recopilar información de empleados de forma natural y eficiente.

OBJETIVO PRINCIPAL:
Recopilar estos datos de manera conversacional:
{required_fields_desc}

DATOS YA RECOPILADOS:
{collected_data}

HISTORIAL DE CONVERSACIÓN:
{conversation_history}

MENSAJE ACTUAL DEL USUARIO:
"{user_message}"

CAMPOS QUE AÚN FALTAN:
{missing_fields}

INTENTO NÚMERO: {attempt_number}

INSTRUCCIONES PARA TU ANÁLISIS:

1. **DETECTAR CANCELACIÓN**: Si el usuario dice palabras como "cancelar", "salir", "no quiero", "adiós", marcar wants_to_cancel=true

2. **EXTRAER INFORMACIÓN**: Del mensaje actual, extraer TODA la información disponible:
   - Nombres completos (Juan Pérez, María García)
   - Emails (cualquier formato, no solo @eroski.es)
   - Nombres de tienda (Eroski + ubicación, o códigos)
   - Secciones (carnicería, caja, panadería, almacén, etc.)

3. **DECIDIR PRÓXIMA ACCIÓN**:
   - Si extraes un email → next_action="search_db" (buscar en base de datos)
   - Si tienes TODOS los campos requeridos → next_action="complete"
   - Si faltan campos → next_action="collect_data"
   - Si el mensaje es confuso → next_action="clarify"

4. **GENERAR MENSAJE NATURAL**:
   - Si extraes email: "Perfecto [nombre], déjame buscar tu información..."
   - Si tienes todo: "¡Excelente! Ya tengo todos tus datos..."
   - Si falta info: "Gracias [nombre/usuario], ¿podrías decirme también [campo específico que falta]?"
   - Si es confuso: "No estoy seguro de entender, ¿podrías repetir [lo que necesitas]?"

5. **SER EFICIENTE**: 
   - Extrae MÚLTIPLE información por mensaje
   - No preguntes datos que ya tienes
   - Personaliza usando el nombre si lo sabes

6. **ACCIONES CUANDO DETECTAS UN EMAIL**: 
   - Enviar el campo "should_search_database" con el valor true,
   - Enviar el campo "email_detected" con el valor true,
   - Personaliza usando el nombre si lo sabes

EJEMPLOS DE RESPUESTAS:

Usuario: "soy Javier Guerra, de Eroski Bilbao, javier.guerra@devol.es, y tengo un problema con la balanza"
→ Extraer: name="Javier Guerra", email="javier.guerra@devol.es", store_name="Eroski Bilbao", section="balanza"
→ email_detected=true, next_action="search_db"

Usuario: "Hola, soy Juan Pérez, mi email es juan@eroski.es, trabajo en Eroski Bilbao Centro"
→ Extraer: name="Juan Pérez", email="juan@eroski.es", store_name="Eroski Bilbao Centro"
→ next_action="search_db"
→ mensaje="¡Hola Juan! Déjame buscar tu información... ¿En qué sección específica ocurrió el problema?"

Usuario: "María García, maria@empresa.com, Eroski Madrid, panadería"
→ Extraer: name="María García", email="maria@empresa.com", store_name="Eroski Madrid", section="panadería"
→ next_action="complete"
→ mensaje="¡Perfecto María! Ya tengo toda tu información..."

Usuario: "trabajo en caja en Eroski"
→ Extraer: section="caja", store_name="Eroski"
→ next_action="collect_data"
→ mensaje="Entiendo que trabajas en caja. ¿Podrías decirme tu nombre y en qué Eroski específico?"

RESPONDE ÚNICAMENTE CON JSON VÁLIDO incluyendo TODOS los campos definidos (aunque sean false):
{{
    "is_complete": false,
    "should_search_database": false,
    "wants_to_cancel": false,
    "email_detected": false,
    "extracted_data": {{}},
    "next_action": "collect_data",
    "message_to_user": "Mensaje natural aquí",
    "missing_fields": [],
    "confidence_level": 0.8
}}
⚠️ IMPORTANTE: No uses formato Markdown. No pongas ```json ni ningún tipo de bloque de código. Solo responde con JSON puro, sin símbolos adicionales.

""",
            input_variables=["user_message", "collected_data", "conversation_history", "missing_fields", "required_fields_desc", "attempt_number"]
        )


# =============================================================================
# FUNCIÓN PARA CREAR INSTANCIA
# =============================================================================

#async def llm_driven_authenticate_node(state: EroskiState) -> Command:
#    """
#    Crear instancia del nodo de autenticación LLM-driven.
#    
#    Returns:
#        Instancia configurada del nodo
#    node = LLMDrivenAuthenticateNode()
#    return node
#    """
#    node = LLMDrivenAuthenticateNode()
#    command = await node.execute(state)
#    state.update(command.update)
#    return state

# ✅ WRAPPER CORREGIDO (solución):
async def llm_driven_authenticate_node(state: EroskiState) -> Command:
    """
    ✅ VERSIÓN CORREGIDA: Retorna Command con goto
    """
    
    logger = logging.getLogger("Node.authenticate")
    logger.info("🔍 === WRAPPER CORREGIDO ===")
    
    try:
        node = LLMDrivenAuthenticateNode()
        command = await node.execute(state)
        
        # ✅ VERIFICAR GOTO
        if hasattr(command, 'goto') and command.goto:
            logger.info(f"✅ GOTO detectado: {command.goto}")
        else:
            logger.info("⚠️ No hay GOTO")
        
        # ✅ RETORNAR COMMAND DIRECTAMENTE
        return command  # ✅ Mantiene goto
        
    except Exception as e:
        logger.error(f"💥 Error: {e}")
        return Command(update={
            **state,
            "error_occurred": True,
            "escalation_needed": True
        })



    #command = await node.execute(state)
    #return {**state, **command.update}

    #node = LLMDrivenAuthenticateNode()
    #command = await node.execute(state)
    #state.update(command.update)
    #return await node.execute(state)

__all__ = ["llm_driven_authenticate_node", "authenticate_employee_node"]