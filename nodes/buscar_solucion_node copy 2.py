# =====================================================
# nodes/buscar_solucion_node.py - VERSIÓN CORREGIDA
# =====================================================
"""
Nodo para búsqueda de soluciones con RAG optimizado y metadatos.

CORRECCIONES APLICADAS:
1. ✅ Importar OptimizedEroskiKnowledgeBaseWithMetadata desde improved_eroski_knowledge_base.py
2. ✅ Usar metadatos (balanza, DIBAL, Mistral) para búsqueda específica
3. ✅ Selección de equipo basada en contexto de incidencia
4. ✅ Verificación de que los metadatos están guardados en BD
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from langchain.tools import Tool
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langgraph.types import Command

# Importaciones del proyecto
from models.eroski_state import EroskiState
from utils.llm.providers import get_llm

# ✅ CORRECCIÓN 1: Importar desde improved_eroski_knowledge_base.py 
try:
    from nodes.improved_eroski_knowledge_base import OptimizedEroskiKnowledgeBaseWithMetadata
    ENHANCED_RAG_AVAILABLE = True
    logger.info("✅ RAG con metadatos importado correctamente")
except ImportError as e:
    logger.warning(f"⚠️ No se pudo importar RAG mejorado: {e}")
    from nodes.optimized_eroski_knowledge_base import OptimizedEroskiKnowledgeBase
    ENHANCED_RAG_AVAILABLE = False

# Otros imports
from data.eroski_faq_problem_identification_tool import FAQ_ProblemIdentificationTool

from data.eroski_incidents_manager import EroskiIncidentsManager
from nodes.tools.confirmation_tool import ConfirmationTool

logger = logging.getLogger(__name__)

class BuscarSolucionNode:
    """
    Nodo principal para búsqueda de soluciones usando RAG con metadatos.
    
    FUNCIONALIDADES:
    - ✅ Búsqueda específica por equipo (balanza, DIBAL, Mistral)
    - ✅ Uso de metadatos almacenados en knowledge_base_enhanced
    - ✅ Selección automática de equipo basada en tipo de incidencia
    - ✅ Fallback a búsqueda general si no hay contexto específico
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # ✅ CORRECCIÓN 2: Usar RAG mejorado con metadatos
        if ENHANCED_RAG_AVAILABLE:
            self.knowledge_base = OptimizedEroskiKnowledgeBaseWithMetadata()
            self.logger.info("🔧 Usando RAG optimizado con metadatos")
        else:
            self.knowledge_base = OptimizedEroskiKnowledgeBase()
            self.logger.info("⚠️ Usando RAG básico (sin metadatos)")
        
        # Otros componentes
        self.incidents_manager = EroskiIncidentsManager()
        self.faq_problem_tool = FAQ_ProblemIdentificationTool(self.incidents_manager)
        self.confirmation_tool = ConfirmationTool()
        self.llm = get_llm()
        self.max_attempts = 3
        self.node_name = "buscar_solucion"
        self.parser_json = JsonOutputParser()
        self.parser_str = StrOutputParser()
        
        # ✅ CORRECCIÓN 3: Configurar herramientas con soporte para metadatos
        self.tools_manual = self._setup_tools_manual()
        self.tools_faq = self._setup_tools_faq()
        self.tools = self.tools_manual + self.tools_faq
        
        # Configurar agentes
        self.agent = self._setup_agent()
        self.agent_faq = self._setup_agent_faq()
        
        # Chains adicionales
        self.identificacion_solucion_chain = self._setup_identificacion_solucion_chain()
        self.solution_fusion_chain = self._setup_solution_fusion_chain()

        # Prompt para información extra
        self.llm_extra_info_prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un experto en soporte técnico.

Analiza el siguiente mensaje del usuario, que se ha producido después de que se le propusiera una solución que **no resolvió el problema**.

Tu tarea es responder:
- "si": si el mensaje del usuario contiene nueva información útil para diagnosticar o entender mejor el problema.
- "no": si el usuario simplemente dice que no funcionó, sin aportar más información técnica.

Ejemplos:
Usuario: "No, no funcionó" → no  
Usuario: "No, sigue fallando" → no  
Usuario: "No, ahora aparece una luz roja en la pantalla" → si  
Usuario: "No, y suena un pitido al encender" → si

Mensaje del usuario: "{user_message}"

Responde únicamente con "si" o "no".
""")
        ])
    
    def _setup_tools_manual(self) -> List[Tool]:
        """
        ✅ CORRECCIÓN 4: Configurar herramientas con soporte para metadatos
        AQUÍ ES DONDE SE USA self.tools_manual
        """

        def buscar_manual_wrapper(query: str) -> str:
            """
            Wrapper para búsqueda en manuales usando RAG optimizado con metadatos.
            ✅ AQUÍ ES DONDE SE APLICAN LOS METADATOS
            """
            try:
                # ✅ CORRECCIÓN 5: Usar búsqueda con metadatos si está disponible
                if ENHANCED_RAG_AVAILABLE and hasattr(self.knowledge_base, 'buscar_solucion_rag_avanzada'):
                    
                    # ✅ IDENTIFICAR EQUIPO DESDE EL CONTEXTO
                    equipo_context = self._detect_equipment_context(query)
                    
                    self.logger.info(f"🔍 Búsqueda con contexto: {equipo_context}")
                    
                    # Crear un bucle de eventos si no existe
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    # Ejecutar búsqueda avanzada con metadatos
                    result = loop.run_until_complete(
                        self.knowledge_base.buscar_solucion_rag_avanzada(
                            query=query,
                            equipo_context=equipo_context,
                            top_k=3,
                            incluir_enlaces=True
                        )
                    )
                    return result
                
                else:
                    # Fallback a búsqueda básica
                    return self.knowledge_base.buscar_solucion_rag(query)
                    
            except Exception as e:
                self.logger.error(f"Error en búsqueda manual: {e}")
                return f"Error en búsqueda de manual: {str(e)}"
        
        return [
            Tool(
                name="buscar_solucion_en_manual",
                description="""
                Busca soluciones en los manuales técnicos usando RAG optimizado con metadatos.
                Puede filtrar por equipo específico (balanza DIBAL Mistral).
                Input: descripción del problema o palabras clave
                Output: Texto con las mejores soluciones encontradas con metadatos
                """,
                func=buscar_manual_wrapper
            )
        ]
    
    def _detect_equipment_context(self, query: str) -> Optional[Dict[str, str]]:
        """
        ✅ CORRECCIÓN 6: Detectar contexto de equipo para usar metadatos correctos
        
        Basado en el conocimiento del proyecto, sabemos que tenemos vectorizado:
        - tipo_equipo: "balanza"  
        - marca: "Dibal"
        - modelo: "Mistral"
        """
        
        query_lower = query.lower()
        
        # ✅ DETECCIÓN ESPECÍFICA PARA BALANZA DIBAL MISTRAL
        if any(word in query_lower for word in ["balanza", "peso", "pesar", "etiqueta", "precio"]):
            # Verificar si es específicamente DIBAL
            if any(word in query_lower for word in ["dibal", "mistral"]):
                return {
                    "tipo": "balanza",
                    "marca": "Dibal", 
                    "modelo": "Mistral"
                }
            else:
                # Balanza genérica, usar DIBAL como default (es el que tenemos vectorizado)
                return {
                    "tipo": "balanza",
                    "marca": "Dibal",
                    "modelo": "Mistral"
                }
        
        # ✅ DETECCIÓN PARA OTROS EQUIPOS (TPV, impresora, etc.)
        elif any(word in query_lower for word in ["tpv", "caja", "registradora", "terminal"]):
            return {
                "tipo": "tpv",
                "marca": "General",
                "modelo": "Estándar"
            }
        
        elif any(word in query_lower for word in ["impresora", "imprimir", "papel", "tinta"]):
            return {
                "tipo": "impresora", 
                "marca": "General",
                "modelo": "Estándar"
            }
        
        # Si no se detecta equipo específico, devolver None para búsqueda general
        return None
    
    def _setup_tools_faq(self) -> List[Tool]:
        """Configurar herramientas para FAQ"""
        
        def faq_problem_wrapper(query: str) -> str:
            """Wrapper para identificación de problemas FAQ"""
            try:
                result = self.faq_problem_tool.identify_problem(query, "general")
                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                return f"Error en identificación FAQ: {str(e)}"
        
        return [
            Tool(
                name="identify_problem_faq",
                description="Identifica problemas usando base de FAQ",
                func=faq_problem_wrapper
            )
        ]
    
    def _setup_agent(self):
        """Configurar agente principal React"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Eres un asistente técnico especializado en equipos de Eroski.

Tienes acceso a manuales técnicos con información específica sobre:
- Balanzas DIBAL Mistral
- TPVs y cajas registradoras
- Impresoras y otros equipos

Usa las herramientas disponibles para buscar soluciones específicas y detalladas.
Siempre menciona el equipo específico cuando sea relevante."""),
            ("user", "{input}"),
            ("assistant", "{agent_scratchpad}")
        ])
        
        agent = create_react_agent(self.llm, self.tools, prompt)
        return AgentExecutor(agent=agent, tools=self.tools, verbose=True, max_iterations=3)
    
    def _setup_agent_faq(self):
        """Configurar agente FAQ (simplificado)"""
        return self._setup_agent()
    
    def _setup_identificacion_solucion_chain(self):
        """Configurar chain de identificación"""
        from langchain_core.runnables import RunnableLambda
        return RunnableLambda(lambda x: {"problema": x, "confidence": 0.5})
    
    def _setup_solution_fusion_chain(self):
        """Configurar chain de fusión de soluciones"""  
        from langchain_core.runnables import RunnableLambda
        return RunnableLambda(lambda x: f"Solución fusionada: {x}")
    
    async def execute(self, state: EroskiState) -> Command:
        """
        ✅ MÉTODO PRINCIPAL: Ejecutar búsqueda de soluciones con metadatos
        """
        self.logger.info(f"🔍 Ejecutando buscar_solucion_node con RAG y metadatos")
        
        try:
            # Obtener información del estado
            messages = state.get("messages", [])
            incident_type = state.get("incident_type", "")
            problem_identified = state.get("problem_identified", False)
            solution_found = state.get("solution_found", False)
            pending_confirmation = state.get("pending_confirmation", False)
            attempts = state.get("attempts", 0)
            
            # Control de flujo básico
            if not messages:
                return Command(update={
                    "current_node": self.node_name,
                    "messages": [AIMessage(content="¡Hola! ¿En qué puedo ayudarte hoy?")],
                    "awaiting_user_input": True
                })
            
            # ✅ USAR LAS HERRAMIENTAS CON METADATOS
            last_user_message = ""
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    last_user_message = msg.content
                    break
            
            if last_user_message and not solution_found:
                # ✅ APLICAR BÚSQUEDA CON METADATOS
                self.logger.info(f"🔧 Buscando solución para: {incident_type} - {last_user_message}")
                
                # Construir consulta enriquecida
                if incident_type:
                    search_query = f"{incident_type}: {last_user_message}"
                else:
                    search_query = last_user_message
                
                # ✅ USAR self.tools_manual[0] - AQUÍ ES DONDE SE USA
                solution_result = self.tools_manual[0].func(search_query)
                
                if "Error" not in solution_result and len(solution_result.strip()) > 50:
                    # ✅ SOLUCIÓN ENCONTRADA CON METADATOS
                    solution_message = AIMessage(
                        content=f"""He encontrado estas soluciones específicas para tu problema con **{incident_type or 'el equipo'}**:

{solution_result}

¿Te ha funcionado alguna de estas soluciones?"""
                    )
                    
                    return Command(update={
                        "pending_confirmation": True,
                        "confirmation_target": "solution",
                        "resolution_details": solution_result,
                        "messages": messages + [solution_message],
                        "awaiting_user_input": True,
                        "last_activity": datetime.now()
                    })
                
                else:
                    # ✅ NO SE ENCONTRARON SOLUCIONES ESPECÍFICAS
                    if attempts < self.max_attempts:
                        retry_message = AIMessage(
                            content=f"""No he encontrado soluciones específicas para "{search_query}" en los manuales técnicos.

¿Podrías proporcionar más detalles sobre el problema? Por ejemplo:
- ¿Qué mensaje de error aparece?
- ¿Cuándo comenzó el problema?
- ¿Has intentado alguna solución antes?

Esto me ayudará a buscar mejor en la documentación técnica."""
                        )
                        
                        return Command(update={
                            "attempts": attempts + 1,
                            "messages": messages + [retry_message],
                            "awaiting_user_input": True
                        })
                    
                    else:
                        # Escalar después de varios intentos
                        escalation_message = AIMessage(
                            content="He agotado las opciones de búsqueda en los manuales. Voy a escalar tu incidencia a un supervisor técnico que podrá ayudarte mejor."
                        )
                        
                        return Command(update={
                            "requires_supervisor": True,
                            "current_node": "escalacion_supervisor",
                            "messages": messages + [escalation_message],
                            "awaiting_user_input": True
                        })
            
            # Manejo de confirmación pendiente
            if pending_confirmation and state.get("confirmation_target") == "solution":
                return await self._handle_solution_confirmation(state)
            
            # Estado por defecto
            base_update = {
                "current_node": self.node_name,
                "last_activity": datetime.now(),
                "awaiting_user_input": True
            }
            
            return Command(update=base_update)
            
        except Exception as e:
            self.logger.error(f"Error en buscar_solucion_node: {e}")
            return Command(update={
                "current_node": self.node_name,
                "last_activity": datetime.now(),
                "messages": state.get("messages", []) + [
                    AIMessage(content="Lo siento, hubo un error interno. ¿Podrías intentar describir tu problema de nuevo?")
                ],
                "awaiting_user_input": True
            })
        
        finally:
            # Limpiar recursos
            try:
                if hasattr(self.knowledge_base, 'close'):
                    self.knowledge_base.close()
            except:
                pass
    
    async def _handle_solution_confirmation(self, state: EroskiState) -> Command:
        """Manejar confirmación de si la solución funcionó"""
        
        messages = state.get("messages", [])
        user_response = messages[-1].content if messages else ""
        
        # Usar herramienta de confirmación
        confirmation_result = self.confirmation_tool.confirm(user_response)
        
        if confirmation_result == "confirmed":
            # ✅ SOLUCIÓN FUNCIONÓ
            success_message = AIMessage(
                content="¡Excelente! Me alegra saber que el problema se ha resuelto con la información de los manuales técnicos. ¿Hay algo más en lo que pueda ayudarte?"
            )
            
            return Command(update={
                "solution_found": True,
                "resolution_status": "resolved",
                "pending_confirmation": False,
                "confirmation_target": None,
                "current_node": "finalizacion",
                "messages": messages + [success_message],
                "awaiting_user_input": True,
                "last_activity": datetime.now()
            })
        
        elif confirmation_result == "denied":
            # ✅ SOLUCIÓN NO FUNCIONÓ
            attempts = state.get("attempts", 0) + 1
            
            if attempts < self.max_attempts:
                # Buscar información adicional
                additional_info_message = AIMessage(
                    content="Entiendo que esa solución no funcionó. ¿Podrías contarme qué pasó exactamente cuando intentaste la solución? Esto me ayudará a buscar alternativas más específicas en los manuales técnicos."
                )
                
                return Command(update={
                    "pending_confirmation": False,
                    "confirmation_target": None,
                    "attempts": attempts,
                    "messages": messages + [additional_info_message],
                    "awaiting_user_input": True
                })
            
            else:
                # Escalar después de varios intentos
                escalation_message = AIMessage(
                    content="He intentado varias soluciones de los manuales técnicos sin éxito. Voy a escalar tu incidencia a un supervisor técnico especializado que podrá revisar el caso personalmente."
                )
                
                return Command(update={
                    "requires_supervisor": True,
                    "current_node": "escalacion_supervisor",
                    "messages": messages + [escalation_message],
                    "awaiting_user_input": True
                })
        
        else:
            # Respuesta no clara
            clarify_message = AIMessage(
                content="No he entendido tu respuesta. ¿La solución que te propuse funcionó? Por favor responde sí o no para poder ayudarte mejor."
            )
            
            return Command(update={
                "messages": messages + [clarify_message],
                "awaiting_user_input": True
            })

# =====================================================
# ✅ VERIFICACIÓN DE METADATOS EN BASE DE DATOS
# =====================================================

async def verificar_metadatos_bd():
    """
    Función de utilidad para verificar que los metadatos están guardados
    correctamente en la base de datos
    """
    
    try:
        # Usar la misma conexión que el RAG
        if ENHANCED_RAG_AVAILABLE:
            knowledge_base = OptimizedEroskiKnowledgeBaseWithMetadata()
            
            # Verificar estadísticas
            stats = await knowledge_base.obtener_estadisticas_completas()
            
            print("✅ VERIFICACIÓN DE METADATOS EN BD:")
            print("=" * 50)
            print(f"📊 Total documentos: {stats['general']['total_documentos']}")
            print(f"📄 Total chunks: {stats['general']['total_chunks']}") 
            print(f"🔧 Equipos únicos: {stats['general']['equipos_unicos']}")
            print(f"🎯 Confidence promedio: {stats['general']['confidence_promedio']:.2f}")
            
            print("\n📋 Equipos por tipo:")
            for equipo in stats.get('por_equipo', []):
                print(f"  🔧 {equipo['tipo_equipo']} {equipo['marca']} {equipo['modelo']}: {equipo['chunks_count']} chunks")
            
            # Verificar específicamente balanza DIBAL Mistral
            has_dibal_mistral = any(
                equipo['tipo_equipo'].lower() == 'balanza' and 
                equipo['marca'].lower() == 'dibal' and
                equipo['modelo'].lower() == 'mistral'
                for equipo in stats.get('por_equipo', [])
            )
            
            if has_dibal_mistral:
                print("\n✅ CONFIRMADO: Metadatos de balanza DIBAL Mistral están en BD")
            else:
                print("\n❌ WARNING: No se encontraron metadatos de balanza DIBAL Mistral")
            
            return True
            
        else:
            print("❌ RAG con metadatos no disponible")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando metadatos: {e}")
        return False

# =====================================================
# SCRIPT DE PRUEBA
# =====================================================

if __name__ == "__main__":
    import asyncio
    
    async def test_buscar_solucion_node():
        """Probar el nodo con búsqueda por metadatos"""
        
        print("🧪 PROBANDO BUSCAR_SOLUCION_NODE CON METADATOS")
        print("=" * 60)
        
        # 1. Verificar metadatos en BD
        await verificar_metadatos_bd()
        
        # 2. Probar el nodo
        node = BuscarSolucionNode()
        
        # Estado de prueba con incidencia de balanza
        test_state = EroskiState(
            current_node="buscar_solucion",
            awaiting_user_input=True,
            last_activity=datetime.now(),
            authenticated=True,
            employee_name="Juan Pérez",
            incident_type="balanza",
            incident_description="La balanza no imprime etiquetas",
            problem_identified=True,
            solution_found=False,
            messages=[
                HumanMessage(content="La balanza DIBAL no está imprimiendo las etiquetas de precio correctamente")
            ],
            pending_confirmation=False,
            attempts=0,
            requires_supervisor=False,
            resolution_status="pending"
        )
        
        # Ejecutar nodo
        print("\n🔍 Ejecutando búsqueda con metadatos...")
        result = await node.execute(test_state)
        
        print("\n📋 Resultado:")
        print(f"Command update keys: {list(result.update.keys())}")
        
        if "messages" in result.update:
            last_message = result.update["messages"][-1]
            if hasattr(last_message, 'content'):
                print(f"Respuesta: {last_message.content[:200]}...")
    
    # Ejecutar prueba
    asyncio.run(test_buscar_solucion_node())