# =====================================================
# CLASIFICACIÓN EN DOS FASES CON ESTADO EroskiState
# =====================================================

from typing import Dict, Any, Optional, List
from typing import get_type_hints

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from datetime import datetime
import logging
from pydantic import BaseModel, Field

from models.eroski_state import EroskiState
from utils.llm.providers import get_llm
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from utils.state_utils import ensure_incident_description

# =============================================================================
# MODELOS PARA LAS DOS FASES
# =============================================================================

class IncidentTypeDecision(BaseModel):
    """Decisión de la FASE 1: Identificación del tipo de incidencia"""
    
    incident_type_identified: bool = Field(description="Si se identificó el tipo de incidencia")
    incident_type: Optional[str] = Field(description="Tipo identificado (balanza, tpv, impresora, etc.)")
    confidence_level: float = Field(description="Confianza en la identificación (0-1)")
    keywords_detected: List[str] = Field(description="Palabras clave que llevaron a la identificación", default=[])
    additional_info: Optional[str] = Field(description="Información adicional relevante detectada", default=None)
    reasoning: str = Field(description="Razonamiento de por qué se identificó este tipo")
    needs_clarification: bool = Field(description="Si necesita más información para identificar", default=False)

class SpecificProblemDecision(BaseModel):
    """Decisión de la FASE 2: Identificación del problema específico"""
    
    problem_identified: bool = Field(description="Si se identificó el problema específico")
    specific_problem: Optional[str] = Field(description="Problema específico del catálogo")
    
    # ✅ FIX CRÍTICO: Hacer problem_description opcional con valor por defecto
    problem_description: Optional[str] = Field(
        description="Descripción del problema (puede ser 'otros')", 
        default="No especificado"
    )
    
    solution_available: bool = Field(description="Si hay solución disponible para este problema")
    proposed_solution: Optional[str] = Field(description="Solución propuesta si está disponible")
    additional_info: Optional[str] = Field(description="Información adicional sobre el problema", default=None)
    confidence_level: float = Field(description="Confianza en la identificación del problema (0-1)")
    next_action: str = Field(description="Próxima acción: provide_solution, ask_details, escalate")
# =============================================================================
# PROMPTS PARA LAS DOS FASES
# =============================================================================

def build_phase_1_prompt() -> PromptTemplate:
    """
    FASE 1: Identificar TIPO de incidencia
    
    Objetivo: Determinar si es balanza, TPV, impresora, red, etc.
    Actualiza: state.incident_type + state.additional_info
    """
    return PromptTemplate(
        template="""Eres un especialista en identificación de TIPOS de incidencias técnicas en Eroski.

🎯 **MISIÓN FASE 1:** Identificar ÚNICAMENTE el TIPO de equipo/sistema con problemas.

EMPLEADO: {employee_name} - Sección: {section} - Tienda: {store_name}

TIPOS DE EQUIPOS DISPONIBLES:
{equipment_types}

HISTORIAL COMPLETO DE MENSAJES:
{conversation_history}

ÚLTIMO MENSAJE: "{user_message}"

🔍 **ANÁLISIS REQUERIDO:**

1️⃣ **Identificar el EQUIPO/SISTEMA:**
   - ¿Menciona directamente un equipo? (balanza, TPV, impresora, ordenador...)
   - ¿Se puede inferir por la sección? (carnicería → probable balanza)
   - ¿Hay palabras clave técnicas? (etiquetas, pantalla, peso, conexión...)

2️⃣ **Evaluar CONFIANZA:**
   - Alta (>0.8): Mención directa o contexto muy claro
   - Media (0.5-0.8): Se puede inferir razonablemente
   - Baja (<0.5): Muy vago o ambiguo

3️⃣ **Capturar INFORMACIÓN ADICIONAL:**
   - Síntomas mencionados
   - Detalles técnicos
   - Contexto temporal (desde cuándo, frecuencia...)

✅ **EJEMPLOS DE IDENTIFICACIÓN CORRECTA:**

**Ejemplo A - Mención directa:**
Usuario: "la balanza no funciona bien"
→ incident_type: "balanza", confidence: 0.95

**Ejemplo B - Inferencia por contexto:**
Usuario: "problema con las etiquetas" + Sección: "carnicería"
→ incident_type: "balanza", confidence: 0.85

**Ejemplo C - Síntoma técnico:**
Usuario: "no puedo cobrar" + Sección: "caja"
→ incident_type: "tpv", confidence: 0.8

**Ejemplo D - Información insuficiente:**
Usuario: "no funciona"
→ incident_type_identified: false, needs_clarification: true

RESPONDE ÚNICAMENTE CON JSON:
{{
  "incident_type_identified": true/false,
  "incident_type": "balanza|tpv|impresora|red|ordenador|telefono|otros",
  "confidence_level": 0.0-1.0,
  "keywords_detected": ["palabra1", "palabra2"],
  "additional_info": "Información relevante detectada",
  "reasoning": "Razón por la que identifiqué este tipo",
  "needs_clarification": true/false
}}""",
        input_variables=[
            "employee_name", "section", "store_name", "equipment_types",
            "conversation_history", "user_message"
        ]
    )

def build_phase_2_prompt() -> PromptTemplate:
    return PromptTemplate(
        template="""🎯 **MISIÓN FASE 2:** Identificar el PROBLEMA ESPECÍFICO dentro de {incident_type}.

INFORMACIÓN DE FASE 1:
- Tipo identificado: {incident_type}
- Información adicional: {phase1_additional_info}
- Confianza Fase 1: {phase1_confidence}

CATÁLOGO DE PROBLEMAS Y SOLUCIONES PARA {incident_type}:
{specific_problems_catalog}

HISTORIAL COMPLETO:
{conversation_history}

ÚLTIMO MENSAJE: "{user_message}"

🔍 **ANÁLISIS DE PROBLEMA ESPECÍFICO:**

1️⃣ **Buscar COINCIDENCIA EXACTA:**
   - ¿El usuario describe exactamente uno de los problemas del catálogo?
   - ¿Usa palabras clave que coinciden directamente?

2️⃣ **Si encuentras coincidencia, USA LA SOLUCIÓN DEL CATÁLOGO:**
   - Si identificas "Error de calibración" → usa su solución específica
   - NO inventes soluciones genéricas, USA LA DEL CATÁLOGO

✅ **EJEMPLO CORRECTO:**
Usuario: "problema de calibración" + Tipo: "balanza"
→ specific_problem: "Error de calibración"
→ proposed_solution: "Limpiar la superficie de pesado y realizar calibración desde el menú de configuración"
→ solution_available: true

RESPONDE ÚNICAMENTE CON JSON VÁLIDO:
{{
  "problem_identified": true/false,
  "specific_problem": "Problema exacto del catálogo o null",
  "problem_description": "Descripción del problema - NUNCA null",
  "solution_available": true/false,
  "proposed_solution": "USAR SOLUCIÓN EXACTA DEL CATÁLOGO o null",
  "additional_info": "Información adicional capturada o null",
  "confidence_level": 0.0-1.0,
  "next_action": "provide_solution|ask_details|escalate"
}}

⚠️ **IMPORTANTE:** 
- Si identificas un problema del catálogo, USA SU SOLUCIÓN EXACTA
- NO inventes soluciones genéricas
- La solución debe venir directamente del catálogo mostrado arriba
""",
        input_variables=[
            "incident_type", "phase1_additional_info", "phase1_confidence",
            "specific_problems_catalog", "conversation_history", "user_message"
        ]
    )

# =============================================================================
# LÓGICA PRINCIPAL DE CLASIFICACIÓN EN DOS FASES
# =============================================================================

class TwoPhaseClassifier:
    """
    Clasificador en dos fases que usa EroskiState como canal de comunicación
    """
    
    def __init__(self):
        self.llm = get_llm()
        self.logger = logging.getLogger("TwoPhaseClassifier")
        
        # Parsers para cada fase
        self.phase1_parser = JsonOutputParser(pydantic_object=IncidentTypeDecision)
        self.phase2_parser = JsonOutputParser(pydantic_object=SpecificProblemDecision)
        
        # Prompts para cada fase
        self.phase1_prompt = build_phase_1_prompt()
        self.phase2_prompt = build_phase_2_prompt()
    
    async def classify_incident(self, state: EroskiState) -> Command:
        """
        Ejecutar clasificación en dos fases usando EroskiState
        
        Args:
            state: Estado actual con mensajes e información del empleado
            
        Returns:
            Command con estado actualizado
        """
        
        # ✅ FASE 1: Identificar TIPO de incidencia
        if not state.get("incident_type"):
            self.logger.info("🔍 FASE 1: Identificando tipo de incidencia...")
            
            phase1_result = await self._execute_phase_1(state)

            print(f"👹Resultados de FASE 1: {phase1_result}")
            
            # Actualizar estado con resultados de FASE 1
            
            if phase1_result.incident_type_identified and phase1_result.confidence_level >= 0.7:
                # Actualizar estado con tipo identificado
                updated_state = self._update_state_after_phase1(state, phase1_result)
                
                self.logger.info(f"✅ FASE 1 COMPLETADA: {phase1_result.incident_type} (confianza: {phase1_result.confidence_level})")
                
                # Continuar inmediatamente a FASE 2
                return await self._execute_phase_2_with_state(updated_state)
            
            elif phase1_result.needs_clarification:
                self.logger.info("👹necesiada de clarificación type")
                # Necesita más información para identificar tipo
                return self._ask_for_type_clarification(state, phase1_result)
            
            else:
                self.logger.info("👹necesiada de clarificación general")
                # Confianza baja, pedir más información
                return self._ask_general_clarification(state)
        
        # ✅ FASE 2: Identificar PROBLEMA ESPECÍFICO
        else:
            print(f"👹get incident type: {state.get('incident_type')}")
            self.logger.info(f"🔍 FASE 2: Identificando problema específico para {state.get('incident_type')}...")
            return await self._execute_phase_2_with_state(state)
    
    async def _execute_phase_1(self, state: EroskiState) -> IncidentTypeDecision:
        """Ejecutar FASE 1: Identificación del tipo"""
        
        name = state.get("employee_name", "No especificado")
        store_name = state.get("store_name", "No especificado")
        section = state.get("department", "No especificado")
        
                # Preparar datos para el prompt
        prompt_data = {
            "employee_name": name,
            "section": section,
            "store_name": store_name,
            "equipment_types": self._get_equipment_types_list(),
            "conversation_history": self._format_conversation_history(state),
            "user_message": self._get_last_user_message(state)
        }
        
        # Ejecutar LLM Fase 1
        formatted_prompt = self.phase1_prompt.format(**prompt_data)
        response = await self.llm.ainvoke(formatted_prompt)
        
        # Parsear respuesta
        decision_data = self.phase1_parser.parse(response.content)
        return IncidentTypeDecision(**decision_data)
    
    async def _execute_phase_2_with_state(self, state: EroskiState) -> Command:
        """Ejecutar FASE 2 con validación mejorada"""
        
        try:
            print(f"🌄Entramos en la fase 2")
            # Ejecutar Fase 2
            phase2_result = await self._execute_phase_2(state)
            
            # ✅ VALIDACIÓN ADICIONAL: Verificar que problem_description no sea None
            if phase2_result.problem_description is None:
                self.logger.warning("⚠️ problem_description es None, aplicando fallback")
                
                # Crear una nueva instancia con valores por defecto
                phase2_result = SpecificProblemDecision(
                    problem_identified=phase2_result.problem_identified,
                    specific_problem=phase2_result.specific_problem,
                    problem_description="Problema no especificado",  # ✅ Valor por defecto
                    solution_available=phase2_result.solution_available,
                    proposed_solution=phase2_result.proposed_solution,
                    additional_info=phase2_result.additional_info,
                    confidence_level=phase2_result.confidence_level,
                    next_action=phase2_result.next_action
                )
            
            # Procesar resultado según el next_action
            if phase2_result.next_action == "provide_solution" and phase2_result.solution_available:
                return self._provide_solution(state, phase2_result)
            
            elif phase2_result.next_action == "ask_details":
                return self._ask_for_problem_details(state, phase2_result)
            
            elif phase2_result.next_action == "escalate":
                return self._escalate_complex_problem(state, phase2_result)
            
            else:
                # Fallback por defecto
                return self._ask_for_more_details(state, phase2_result)
                
        except Exception as e:
            self.logger.error(f"❌ Error en Fase 2: {e}")
            
            # ✅ MANEJO ROBUSTO DE ERRORES
            return Command(
                update={
                    **state,
                    "last_error": f"Error en clasificación: {str(e)}",
                    "escalation_needed": True
                },
                graph=self._create_error_response_with_escalation(state, str(e))
            )


    
# Añadir este método a la clase TwoPhaseClassifier en utils/two_phase_classifier.py

    async def _execute_phase_2(self, state: EroskiState) -> SpecificProblemDecision:
        """
        Ejecutar FASE 2: Identificación del problema específico
        
        Args:
            state: Estado actual con incident_type ya identificado
            
        Returns:
            SpecificProblemDecision con el resultado de la fase 2
        """
        
        incident_type = state.get("incident_type")
        if not incident_type:
            self.logger.error("❌ FASE 2: incident_type no encontrado en estado")
            # Crear respuesta de error
            return SpecificProblemDecision(
                problem_identified=False,
                specific_problem=None,
                problem_description="Error: tipo de incidencia no identificado",
                solution_available=False,
                proposed_solution=None,
                additional_info=None,
                confidence_level=0.0,
                next_action="escalate"
            )
        
        auth_data = state.get("auth_data_collected", {})
        
        # Preparar datos para el prompt de FASE 2
        prompt_data = {
            "incident_type": incident_type,
            "phase1_additional_info": state.get("additional_info", "Ninguna información adicional"),
            "phase1_confidence": state.get("confidence_score", 0.8),
            "specific_problems_catalog": self._get_specific_problems_for_type(incident_type),
            "conversation_history": self._format_conversation_history(state),
            "user_message": self._get_last_user_message(state)
        }
        
        self.logger.info(f"🔍 FASE 2: Analizando problema específico para {incident_type}")
        self.logger.debug(f"📋 Catálogo de problemas: {prompt_data['specific_problems_catalog']}")
        
        try:
            # Ejecutar LLM con prompt de FASE 2
            formatted_prompt = self.phase2_prompt.format(**prompt_data)
            
            self.logger.debug(f"📝 Prompt FASE 2 generado (primeros 200 chars): {formatted_prompt[:200]}...")
            
            response = await self.llm.ainvoke(formatted_prompt)
            
            self.logger.debug(f"🤖 Respuesta LLM FASE 2: {response.content}")
            
            # Parsear respuesta JSON
            decision_data = self.phase2_parser.parse(response.content)
            
            # ✅ VALIDACIÓN CRÍTICA: Asegurar que problem_description no sea None
            if decision_data.get("problem_description") is None:
                self.logger.warning("⚠️ problem_description es None, aplicando fallback")
                decision_data["problem_description"] = "Problema no especificado claramente"
            
            # Crear objeto SpecificProblemDecision
            phase2_result = SpecificProblemDecision(**decision_data)
            
            self.logger.info(f"✅ FASE 2 completada: problema='{phase2_result.problem_description}', acción='{phase2_result.next_action}'")
            
            return phase2_result
            
        except Exception as e:
            self.logger.error(f"❌ Error en FASE 2: {e}")
            self.logger.error(f"Respuesta raw que causó error: {getattr(response, 'content', 'N/A')}")
            
            # Fallback: Crear decisión de escalación
            return SpecificProblemDecision(
                problem_identified=False,
                specific_problem=None,
                problem_description=f"Error técnico en clasificación: {str(e)}",
                solution_available=False,
                proposed_solution=None,
                additional_info=f"Error técnico: {str(e)}",
                confidence_level=0.0,
                next_action="escalate"
            )


    def _get_specific_problems_for_type(self, incident_type: str) -> str:
        """
        Cargar problemas Y soluciones directamente del JSON para que el LLM las use
        """
        
        try:
            import json
            from pathlib import Path
            
            # ✅ CARGAR DIRECTAMENTE desde scripts/eroski_incidents.json
            scripts_file = Path("scripts/eroski_incidents.json")
            if not scripts_file.exists():
                self.logger.error("❌ No existe scripts/eroski_incidents.json")
                return f"• Problemas técnicos relacionados con {incident_type}"
            
            with open(scripts_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Buscar el tipo en la estructura
            incident_types = data.get("incident_types", {})
            incident_data = incident_types.get(incident_type)
            
            if not incident_data:
                self.logger.warning(f"⚠️ Tipo '{incident_type}' no encontrado en scripts/")
                return f"• Problemas técnicos relacionados con {incident_type}"
            
            # ✅ OBTENER PROBLEMAS Y SOLUCIONES
            problemas = incident_data.get("problemas", {})
            
            if not problemas:
                self.logger.warning(f"⚠️ No hay 'problemas' para {incident_type}")
                return f"• Problemas técnicos relacionados con {incident_type}"
            
            # ✅ FORMATEAR PARA QUE EL LLM VEA PROBLEMAS Y SOLUCIONES
            formatted_catalog = []
            
            for problema, solucion in problemas.items():
                # Formato claro para el LLM
                formatted_catalog.append(f"""**{problema}**
    Solución: {solucion}""")
            
            result = "\n\n".join(formatted_catalog)
            
            self.logger.info(f"✅ Cargados {len(problemas)} problemas CON soluciones para {incident_type}")
            self.logger.info(f"📋 Ejemplo: 'Error de calibración' -> 'Limpiar la superficie de pesado...'")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Error cargando desde scripts/: {e}")
            return f"• Problemas técnicos relacionados con {incident_type}"

    def _get_fallback_problems(self, incident_type: str) -> str:
        """Obtener problemas hardcodeados como fallback"""
        
        self.logger.info(f"🔄 Usando fallback para {incident_type}")
        
        fallback_problems = {
            "balanza": """• **No enciende**
    • **No imprime etiquetas**
    • **Las etiquetas salen en blanco**
    • **Error de calibración**
    • **Precio incorrecto en etiquetas**
    • **No lee códigos de barras**
    • **Pantalla borrosa o dañada**
    • **Problemas de conectividad**""",
            
            "balanzas": """• **No imprime etiquetas**
    • **Peso incorrecto**
    • **Error de calibración**
    • **Pantalla no funciona**
    • **No se conecta al sistema**
    • **Precios incorrectos en etiquetas**""",
            
            "tpv": """• **TPV no enciende**
    • **No lee tarjetas de crédito**
    • **Error en el cajón de efectivo**
    • **Problemas con el lector de códigos de barras**
    • **La pantalla táctil no responde**
    • **No imprime tickets**
    • **Error de comunicación con el servidor**""",
            
            "impresora": """• **No imprime documentos**
    • **Impresión borrosa o con líneas**
    • **Atasco de papel**
    • **Error de tinta o tóner**
    • **No reconoce el formato de papel**
    • **Problemas de conectividad**""",
            
            "red": """• **Sin conexión a internet**
    • **WiFi muy lento**
    • **No puede acceder a aplicaciones corporativas**
    • **Error de conexión intermitente**
    • **Problemas con VPN**""",
            
            "ordenador": """• **El ordenador no enciende**
    • **Pantalla azul o error del sistema**
    • **Muy lento al trabajar**
    • **No reconoce dispositivos USB**
    • **Problemas con aplicaciones específicas**""",
            
            "telefono": """• **No hay línea telefónica**
    • **No se escucha al otro lado**
    • **Problemas con extensiones internas**
    • **Error en el sistema de intercomunicación**"""
        }
        
        return fallback_problems.get(incident_type, f"• Problemas técnicos relacionados con {incident_type}")

    def _update_state_after_phase1(self, state: EroskiState, phase1_result: IncidentTypeDecision) -> EroskiState:
        """Actualizar estado después de FASE 1"""
        
        updated_state = dict(state)
        
        # Actualizar campos del estado
        updated_state.update({
            "incident_type": phase1_result.incident_type,
            "additional_info": phase1_result.additional_info,
            "confidence_score": phase1_result.confidence_level,
            "last_activity": datetime.now()
        })
        
        return EroskiState(updated_state)

    # ✅ TAMBIÉN FALTA ESTE MÉTODO UTILITARIO
    def _get_equipment_types_list(self) -> str:
        """Obtener lista de tipos de equipamiento disponibles"""
        
        try:
            from config.incident_config import IncidentConfigLoader
            config_loader = IncidentConfigLoader()
            incident_types = config_loader.get_incident_types()
            
            # Formatear tipos para el prompt
            formatted_types = []
            for incident_type, data in incident_types.items():
                description = data.get("description", f"Problemas con {incident_type}")
                formatted_types.append(f"• **{incident_type}**: {description}")
            
            return "\n".join(formatted_types)
            
        except Exception as e:
            self.logger.error(f"❌ Error cargando tipos de equipamiento: {e}")
            
            # Fallback hardcodeado
            return """
    • **balanza**: Problemas con balanzas de pesaje y etiquetado
    • **tpv**: Problemas con terminales punto de venta
    • **impresora**: Problemas con impresoras de documentos y etiquetas
    • **red**: Problemas de conectividad y red
    • **ordenador**: Problemas con ordenadores y sistemas
    • **telefono**: Problemas con sistemas telefónicos
    """
    
    def _process_phase2_result(self, state: EroskiState, phase2_result: SpecificProblemDecision) -> Command:
        """Procesar resultado de FASE 2 y generar respuesta"""
        
        # Actualizar estado con resultado de FASE 2
        updated_state = dict(state)

        # Combinar información adicional de ambas fases
        existing_additional_info = updated_state.get("additional_info", "")
        new_additional_info = phase2_result.additional_info or ""
        
        if new_additional_info and existing_additional_info:
            combined_info = f"{existing_additional_info} | {new_additional_info}"
        else:
            combined_info = new_additional_info or existing_additional_info
        
        updated_state.update({
            "incident_description": phase2_result.problem_description,
            "solution_found": phase2_result.solution_available,
            "solution_content": phase2_result.proposed_solution,
            "last_activity": datetime.now()
        })
        

        updated_state = ensure_incident_description(updated_state)

        
        
        updated_state["additional_info"] = combined_info
        
        # Decidir próxima acción basada en el resultado
        if phase2_result.next_action == "provide_solution" and phase2_result.solution_available:
            return self._provide_solution(updated_state, phase2_result)
        
        elif phase2_result.next_action == "ask_details":
            return self._ask_for_problem_details(updated_state, phase2_result)
        
        elif phase2_result.next_action == "escalate":
            return self._escalate_complex_problem(updated_state, phase2_result)
        
        else:
            # Fallback: pedir más detalles
            return self._ask_for_problem_details(updated_state, phase2_result)

    def _provide_solution(self, state: EroskiState, phase2_result: SpecificProblemDecision) -> Command:
        """Proporcionar solución identificada y actualizar persistencia completa"""
        
        incident_code = state.get("incident_code", "N/A")
        
        solution_message = f"""✅ **Problema identificado: {state.get('incident_type', '').title()}**

    📋 **Problema específico:** {phase2_result.specific_problem}

    🔧 **Solución paso a paso:**
    {phase2_result.proposed_solution}

    🤔 **¿Quieres intentar esta solución?**
    - Responde **'sí'** para que te guíe paso a paso
    - Responde **'no entiendo'** si necesitas más explicación
    - Responde **'ya lo intenté'** si ya probaste esto

    📋 *Código de incidencia: {incident_code}*"""

        # ✅ ACTUALIZAR PERSISTENCIA COMPLETA CON MENSAJES
        try:
            from pathlib import Path
            import json
            from datetime import datetime
            from langchain_core.messages import HumanMessage, AIMessage
            
            incidents_file = Path("incidents_database.json")
            
            if incidents_file.exists():
                with open(incidents_file, 'r', encoding='utf-8') as f:
                    incidents_data = json.load(f)
                
                if incident_code in incidents_data:
                    
                    # Actualizar datos de clasificación
                    incidents_data[incident_code].update({
                        "tipo_incidencia": state.get("incident_type"),
                        "problema_especifico": phase2_result.specific_problem,
                        "solucion_aplicada": phase2_result.proposed_solution,
                        "estado_solucion": "propuesta",
                        "timestamp_actualizacion": datetime.now().isoformat()
                    })
                    
                    # ✅ GUARDAR TODOS LOS MENSAJES
                    messages = state.get("messages", [])
                    all_messages = messages + [AIMessage(content=solution_message)]
                    
                    serialized_messages = []
                    for msg in all_messages:
                        if isinstance(msg, HumanMessage):
                            serialized_messages.append({
                                "tipo": "usuario",
                                "contenido": msg.content,
                                "timestamp": datetime.now().isoformat()
                            })
                        elif isinstance(msg, AIMessage):
                            serialized_messages.append({
                                "tipo": "bot",
                                "contenido": msg.content,
                                "timestamp": datetime.now().isoformat()
                            })
                    
                    # Asegurar que incident_description exista
                    state = ensure_incident_description(state)
                    
                    incidents_data[incident_code]["mensajes"] = serialized_messages
                    
                    with open(incidents_file, 'w', encoding='utf-8') as f:
                        json.dump(incidents_data, f, indent=2, ensure_ascii=False)
                    
                    self.logger.info(f"✅ Persistencia y mensajes actualizados para {incident_code}")
                    self.logger.info(f"   - Mensajes guardados: {len(serialized_messages)}")
            
        except Exception as e:
            self.logger.error(f"❌ Error actualizando persistencia: {e}")
        
        return Command(
            update={
                **state,
                "messages": state["messages"] + [AIMessage(content=solution_message)],
                "current_step": "verify_solution",
                "awaiting_user_input": True,
                "solution_provided": True
            }
        )

    def _update_incident_persistence(self, incident_code: str, updates: Dict[str, Any]) -> bool:
        """Método auxiliar para actualizar persistencia"""
        try:
            from pathlib import Path
            import json
            from datetime import datetime
            
            incidents_file = Path("incidents_database.json")
            
            if not incidents_file.exists():
                self.logger.warning(f"⚠️ Archivo de incidencias no existe: {incidents_file}")
                return False
            
            # Cargar datos existentes
            with open(incidents_file, 'r', encoding='utf-8') as f:
                incidents_data = json.load(f)
            
            # Verificar que existe el registro
            if incident_code not in incidents_data:
                self.logger.warning(f"⚠️ Incidencia {incident_code} no encontrada en persistencia")
                return False
            
            # Actualizar registro
            incidents_data[incident_code].update(updates)
            incidents_data[incident_code]["timestamp_actualizacion"] = datetime.now().isoformat()
            
            # Guardar archivo
            with open(incidents_file, 'w', encoding='utf-8') as f:
                json.dump(incidents_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"✅ Incidencia {incident_code} actualizada en persistencia")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error actualizando persistencia: {e}")
            return False
    
    def _ask_for_problem_details(self, state: EroskiState, phase2_result: SpecificProblemDecision) -> Command:
        """Pedir más detalles sobre el problema"""
        
        incident_type = state.get("incident_type", "equipo")
        
        if phase2_result.problem_description == "otros":
            # Problema no catalogado
            message = f"""🔍 **Problema con {incident_type.title()} - Información adicional necesaria**

He identificado que tienes un problema con **{incident_type}**, pero necesito más detalles específicos para ayudarte mejor.

📋 **Por favor, describe:**
• ¿Qué síntomas observas exactamente?
• ¿Cuándo empezó el problema?
• ¿Has intentado algo para solucionarlo?
• ¿Aparece algún mensaje de error?

💡 *Cuanto más específico seas, mejor podré ayudarte*"""
        
        else:
            # Información insuficiente para identificar problema específico
            available_problems = self._get_specific_problems_for_type(incident_type)
            
            message = f"""🔍 **Problema con {incident_type.title()} - ¿Cuál es tu caso específico?**

He identificado que el problema es con **{incident_type}**. Para darte la solución exacta, ¿cuál de estos describe mejor tu situación?

{available_problems}

📝 **O describe tu problema con más detalle si no coincide con ninguno de estos.**"""
        
        return Command(
            update={
                "messages": state["messages"] + [AIMessage(content=message)],
                "current_step": "collect_details",
                "awaiting_user_input": True
            }
        )
    
    # ========== MÉTODOS AUXILIARES ==========

    def _format_conversation_history(self, state: EroskiState) -> str:
        """Formatear historial de conversación"""
        messages = state.get("messages", [])
        formatted = []
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted.append(f"👤 Usuario: {msg.content}")
            elif isinstance(msg, AIMessage):
                formatted.append(f"🤖 Asistente: {msg.content}")
        
        return "\n".join(formatted) if formatted else "Sin historial previo"
    
    def _get_last_user_message(self, state: EroskiState) -> str:
        """Obtener último mensaje del usuario"""
        messages = state.get("messages", [])
        
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return msg.content
        
        return ""

    def _get_specific_problems_for_type(self, incident_type: str) -> str:
        """
        Obtener una muestra de hasta 3 problemas específicos y sus soluciones para un tipo de incidencia.
        """

        try:
            from config.incident_config import IncidentConfigLoader
            config_loader = IncidentConfigLoader()
            incident_types = config_loader.get_incident_types()

            incident_data = incident_types.get(incident_type)
            problemas = config_loader.get_incidentes_problemas()
            problemas_soluc= problemas[incident_type]
            if not incident_data:
                self.logger.warning(f"⚠️ Tipo de incidencia '{incident_type}' no encontrado en la configuración")
                return f"• Problemas técnicos relacionados con {incident_type}"

            
            
            if not isinstance(problemas_soluc, dict) or not problemas_soluc:
                self.logger.warning(f"⚠️ No hay problemas definidos para el tipo '{incident_type}'")
                return f"• Problemas técnicos relacionados con {incident_type}"

            # Seleccionar hasta 3 problemas como ejemplo
            formatted = []
            for i, (problema, solucion) in enumerate(problemas_soluc.items()):
                if i >= 3:
                    break
                formatted.append(f"""**{problema}**  
            Solución: {solucion}""")

            result = "\n\n".join(formatted)
            result += f"\n\n💡 Estos son solo algunos ejemplos comunes con el equipo **{incident_type}**. ¿Podrías describirme tu problema concreto?"

            return result

        except Exception as e:
            self.logger.error(f"❌ Error cargando catálogo de problemas: {e}")
            return f"• Problemas técnicos relacionados con {incident_type}"
 

    def _get_equipment_types_list(self) -> str:
        """Obtener lista de tipos de equipamiento disponibles"""
        
        try:
            from config.incident_config import IncidentConfigLoader
            config_loader = IncidentConfigLoader()
            incident_types = config_loader.get_incident_types()
            
            # Formatear tipos para el prompt
            formatted_types = []
            
            for incident_type, data in incident_types.items():
                # ✅ MANEJAR DIFERENTES TIPOS DE DATOS
                if isinstance(data, dict):
                    description = data.get("description", f"Problemas con {incident_type}")
                    name = data.get("name", incident_type.title())
                else:
                    # Si no es diccionario, usar valores por defecto
                    description = f"Problemas con {incident_type}"
                    name = incident_type.title()
                
                formatted_types.append(f"• **{incident_type}**: {description}")
            
            return "\n".join(formatted_types)
            
        except Exception as e:
            self.logger.error(f"❌ Error cargando tipos de equipamiento: {e}")
            
            # Fallback hardcodeado
            return """• **balanza**: Problemas con balanzas de pesaje y etiquetado
    • **tpv**: Problemas con terminales punto de venta
    • **impresora**: Problemas con impresoras de documentos y etiquetas
    • **red**: Problemas de conectividad y red
    • **ordenador**: Problemas con ordenadores y sistemas
    • **telefono**: Problemas con sistemas telefónicos"""

    def _escalate_complex_problem(self, state: EroskiState, phase2_result: SpecificProblemDecision) -> Command:
        """Escalar problema complejo"""
        
        incident_code = state.get("incident_code", "N/A")
        
        escalation_message = f"""🔝 **Escalando tu incidencia**

    He analizado tu problema pero requiere atención especializada.

    📋 **Resumen:**
    • Tipo: {state.get('incident_type', 'No identificado')}
    • Descripción: {phase2_result.problem_description}
    • Código: {incident_code}

    Un supervisor se pondrá en contacto contigo para resolver esta incidencia.

    ¿Hay alguna información adicional que quieras añadir antes de escalar el caso?"""

        updated_state = {
            **state,
            "messages": state["messages"] + [AIMessage(content=escalation_message)],
            "current_node": "escalate",
            "escalation_needed": True,
            "escalation_reason": "Problema complejo identificado en clasificación"
        }
        
        return Command(update=updated_state)

    def _ask_for_type_clarification(self, state: EroskiState, phase1_result: IncidentTypeDecision) -> Command:
        """Pedir clarificación del tipo de incidencia"""
        
        clarification_message = f"""🤔 **Necesito aclarar el tipo de equipo**

    {phase1_result.reasoning}

    Por favor, especifica qué tipo de equipo está dando problemas:

    • **Balanza** - Problemas con balanzas de pesaje
    • **TPV** - Terminal punto de venta  
    • **Impresora** - Impresoras de etiquetas o documentos
    • **Ordenador** - PC o sistema informático
    • **Red** - Problemas de conectividad
    • **Teléfono** - Sistema telefónico

    ¿Cuál de estos equipos está presentando el problema?"""
        for key, value in state.items():
            print(f"👹{key}: {value}")
        updated_state = {
            **state,
            "messages": [AIMessage(content=clarification_message)],
            "current_node": "classify",
            "awaiting_type_clarification": True
        }
        
        return Command(update=updated_state)

    def _ask_general_clarification(self, state: EroskiState) -> Command:
        """Pedir clarificación general"""
        
        clarification_message = """❓ **Necesito más información**

    Para ayudarte de la mejor manera, necesito que me proporciones más detalles sobre el problema:

    • ¿Qué equipo está dando problemas? (balanza, TPV, impresora, etc.)
    • ¿Qué síntomas específicos observas?
    • ¿Cuándo comenzó el problema?

    Por favor, describe la situación con el mayor detalle posible."""

        updated_state = {
            **state,
            "messages": state["messages"] + [AIMessage(content=clarification_message)],
            "current_node": "classify",
            "awaiting_clarification": True
        }
        
        return Command(update=updated_state)

    def _escalate_error(self, state: EroskiState) -> Command:
        """Escalar por error técnico"""
        
        error_message = """⚠️ **Error Técnico**

    Ha ocurrido un problema durante el análisis de tu incidencia. 

    Por favor, contacta con un supervisor o intenta describir tu problema nuevamente.

    Disculpa las molestias."""

        updated_state = {
            **state,
            "messages": state["messages"] + [AIMessage(content=error_message)],
            "current_node": "escalate",
            "escalation_needed": True,
            "escalation_reason": "Error técnico en clasificación"
        }
        
        return Command(update=updated_state)



# =============================================================================
# INTEGRACIÓN CON EL NODO CLASSIFY
# =============================================================================

async def execute_two_phase_classification(state: EroskiState) -> Command:
    """
    Función principal para ejecutar clasificación en dos fases
    
    Args:
        state: Estado actual con EroskiState
        
    Returns:
        Command con estado actualizado
    """
    
    classifier = TwoPhaseClassifier()
    return await classifier.classify_incident(state)
