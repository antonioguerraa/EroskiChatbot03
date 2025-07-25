import json
import pprint
import logging
from typing import Any, Dict, Optional, List
from datetime import datetime
from langchain_core.messages import AIMessage
from langgraph.types import Command

from models.eroski_state import EroskiState
from models.ordenar_chunks import OrdenarChunks
from utils.llm.providers import get_llm
from nodes.improved_eroski_knowledge_base import OptimizedEroskiKnowledgeBaseWithMetadata
from nodes.buscar_solucion_node import BuscarSolucionNode
from utils.cargar_incidentes import EroskiIncidentsManager
from utils.construir_historico_mensajes import format_full_chat_history
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from utils.incident_manager import get_incident_manager

logger = logging.getLogger(__name__)


class FAQ_ProblemIdentificationTool:
    """Herramienta para identificar problemas usando el archivo JSON de incidencias frecuentes."""
    
    def __init__(self, incidents_manager: EroskiIncidentsManager):
        self.incidents_manager = incidents_manager
        self.llm = get_llm()
    
    def identify_problem(self, user_input: str, incident_type: str) -> Dict[str, Any]:
        """
        Identifica el problema específico basándose en el archivo JSON.
        """
        try:
            problems = self.incidents_manager.get_problems_for_type(incident_type)
            
            if not problems:
                return {
                    "problema": f"Problema con {incident_type}",
                    "confidence": 0.5,
                    "keywords": [incident_type],
                    "solucion": "Información no disponible en FAQ",
                    "similar_a_ejemplo": False,
                    "requiere_mas_info": True,
                    "solution_source": "JSON"
                }
            
            # Crear prompt para el LLM
            problems_text = "\n".join([f"- {prob}: {sol[:100]}..." for prob, sol in problems.items()])
            
            prompt = f"""
Analiza el mensaje del usuario y encuentra el problema más similar en la lista de problemas frecuentes.

MENSAJE DEL USUARIO: "{user_input}"

PROBLEMAS FRECUENTES PARA {incident_type.upper()}:
{problems_text}

Responde en JSON con:
- "problema": el problema más similar de la lista (texto exacto)
- "confidence": nivel de confianza 0.0-1.0
- "keywords": palabras clave relevantes del mensaje del usuario
- "solucion": la solución correspondiente del problema identificado
- "similar_a_ejemplo": true si hay alta similitud, false si no
- "requiere_mas_info": true si necesitas más información del usuario

Respuesta JSON:
"""
            
            response = self.llm.invoke(prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Parsear respuesta JSON
            try:
                result = json.loads(response_text)
                result["solution_source"] = "JSON"
                return result
            except json.JSONDecodeError:
                # Fallback si el JSON no es válido
                return self._fallback_identification(user_input, incident_type, problems)
                
        except Exception as e:
            logger.error(f"Error en identificación de problema: {e}")
            return self._fallback_identification(user_input, incident_type, {})
    
    def _fallback_identification(self, text: str, incident_type: str, problems: Dict[str, str]) -> Dict[str, Any]:
        """Identificación de fallback cuando falla el LLM."""
        logger.warning(f"Usando identificación de fallback para: {text[:200]}")
        return {
            "problema": f"Error procesando consulta sobre {incident_type}",
            "confidence": 0.0,
            "keywords": [],
            "solucion": "",
            "similar_a_ejemplo": False,
            "requiere_mas_info": True,
            "solution_source": "Otros"
        }

async def orquestador_busqueda_node(state: EroskiState) -> dict:
    """
    Wrapper para LangGraph - Nodo orquestador de búsqueda de soluciones.
    """
    buscar_soluciones = BuscarSolucionNode()
    node = OrquestadorBusquedaNode(
        knowledge_base=OptimizedEroskiKnowledgeBaseWithMetadata(),
        faq_tool=FAQ_ProblemIdentificationTool(EroskiIncidentsManager()),
        ordenar_chunks_chain=buscar_soluciones.setup_ordenar_chunks_chain(),
        agent_faq=buscar_soluciones.setup_agent_faq()
    )
    return await node.execute(state)

class ResultadoBusquedaUnificada:
    def __init__(
        self,
        solution_found: bool,
        solution_content: str,
        confidence_rag: float = 0.0,
        confidence_faq: float = 0.0,
        source_rag: Optional[str] = None,
        source_faq: Optional[str] = None,
    ):
        self.solution_found = solution_found
        self.solution_content = solution_content
        self.confidence_rag = confidence_rag
        self.confidence_faq = confidence_faq
        self.source_rag = source_rag
        self.source_faq = source_faq

class OrquestadorBusquedaNode:
    """
    Nodo de fusión de soluciones desde RAG y JSON de incidencias frecuentes.
    """

    def __init__(self, knowledge_base, faq_tool, ordenar_chunks_chain, agent_faq):
        self.knowledge_base = knowledge_base
        self.faq_tool = faq_tool
        self.ordenar_chunks_chain = ordenar_chunks_chain
        self.agent_faq = agent_faq
        self.logger = logging.getLogger(__name__)

    async def execute(self, state: EroskiState) -> dict:
        print("👹👹👹 Entra en el orquestador de búsqueda 👹👹👹")
        get_incident_manager().manage_incident(state)

        
        try:
            incident_type = state.get("incident_type")
            consulta = state.get("problem_description")
            mensajes = state.get("messages", [])
            chat_history = format_full_chat_history(mensajes)
            logging.info(f"👹 chat_history: {chat_history}")
            logging.info(f"👹 mensajes: {mensajes}")

            base_update = {
                "current_node": "orquestador_busqueda",
                "last_activity": datetime.now()
            }



            # --- 1. Buscar en manual (RAG) ---
            top_k = 3
            resultado_manual = await self.knowledge_base.buscar_solucion_rag_avanzada(
                query=consulta,
                equipo_context={"tipo": incident_type},
                top_k=top_k,
                return_formato="json"
            )
            if resultado_manual['results']:
                lista_chunk = await self._procesar_chunks(resultado_manual)

            #logging.info(f"👹 lista_chunk: {lista_chunk}")

                rag_result = await self.ordenar_chunks_chain.ainvoke({
                    "lista_chunks": lista_chunk,
                    "top_k": top_k,
                    "chat_history": chat_history
                })

                chunck_list = rag_result.get("chunk_id_list", [])

            # --- 2. Buscar en JSON (FAQ) ---
            problemas_dict = self.faq_tool.incidents_manager.get_problemas_soluciones(incident_type)

            faq_result = await self.agent_faq.ainvoke({
                "problema_identificado": consulta,
                "problemas_json": json.dumps(problemas_dict, indent=2, ensure_ascii=False)
            })

            # --- 3. Fusionar resultados ---
            mensajes = []
            if resultado_manual['results'] and rag_result.get("problem_identified"):
                mensajes.append(f"📘 Manual:\n{rag_result['solution_content']}")
            print("👹check 4")
            if faq_result.get("problem_identified"):
                mensajes.append(f"📋 FAQ:\n{faq_result['solution_content']}")

            print(f"👹check 5 mensajes: {mensajes}")
            if not mensajes:
                msg = "Lo siento, no se encontró solución en el manual ni en las incidencias frecuentes. ¿Podrías darme más información?"
                return {
                    **base_update,
                    "messages": [AIMessage(content=msg)],
                    "awaiting_user_input": True,
                    "problem_identified": False
                }

            msg_IA = "\n\n".join(mensajes) + "\n\n¿Resuelve esto tu cuestión?"

            return {
                **base_update,
                "messages": [AIMessage(content=msg_IA)],
                "awaiting_user_input": True,
                "problem_identified": False
            }

        except Exception as e:
            self.logger.error(f"❌ Error en OrquestadorBusquedaNode: {e}")
            return {
                "current_node": "orquestador_busqueda",
                "last_activity": datetime.now(),
                "messages": [AIMessage(content="Lo siento, hubo un error al buscar la solución.")],
                "awaiting_user_input": True
            }

    async def _procesar_chunks(self, resultado_manual: Dict[str, Any]) -> str:
        chunks_list = []
        for item in resultado_manual['results']:
            chunks = await self.knowledge_base.get_chunk_with_context(item['chunk_id'])
            chunks_list.append({
                'chunk_id': item['chunk_id'],
                'page': item['documento']['pagina_numero'],
                'text': (
                    chunks['chunk_anterior']['chunk_text'] + "\n" +
                    chunks['chunk_actual']['chunk_text'] + "\n" +
                    chunks['chunk_siguiente']['chunk_text']
                )
            })

        return "\n\n".join(
            f"[{i+1}] (chunk_id {c['chunk_id']})\npágina {c['page']})\n{c['text']}"
            for i, c in enumerate(chunks_list)
        )
    
 