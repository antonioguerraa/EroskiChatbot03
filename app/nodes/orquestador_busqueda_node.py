import json
import pprint
import logging
import os
from typing import Any, Dict, Optional, List
from datetime import datetime
from langchain_core.messages import AIMessage
from langgraph.types import Command

from app.models.eroski_state import EroskiState
from app.models.ordenar_chunks import OrdenarChunks
from app.utils.llm.providers import get_llm
from app.nodes.improved_eroski_knowledge_base import OptimizedEroskiKnowledgeBaseWithMetadata
from app.nodes.buscar_solucion_node import BuscarSolucionNode
from app.utils.cargar_incidentes import EroskiIncidentsManager
from app.utils.construir_historico_mensajes import format_full_chat_history
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from app.utils.incident_manager import get_incident_manager
from app.utils.document_link_generator import DocumentLinkGenerator
from app.utils.multicanal import renderizar_enlace

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
        
        # Obtener URL base de variable de entorno o usar localhost por defecto
        base_url = os.getenv("PUBLIC_URL", "http://localhost:8000")
        self.link_generator = DocumentLinkGenerator(base_url=base_url)
        
        self.logger = logging.getLogger(__name__)
        self.chunks_metadata = {}
        
        self.logger.info(f"🌐 OrquestadorBusquedaNode usando URL base: {base_url}")

    async def execute(self, state: EroskiState) -> dict:
        print("👹👹👹 Entra en el orquestador de búsqueda 👹👹👹")
        print(f"🔍 Canal detectado: {state.get('channel', 'No especificado')}")
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
                lista_chunk = await self._procesar_chunks_con_metadatos(resultado_manual)
        

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

            # --- 3. Fusionar resultados CON ENLACES ---
            mensajes = []
            if resultado_manual['results'] and rag_result.get("problem_identified"):
                # MODIFICADO: Generar solución con enlaces
                solucion_con_enlaces = await self._generar_solucion_con_enlaces(
                    state,
                    rag_result['solution_content'], 
                    chunck_list
                )
                mensajes.append(f"📘 Manual:\n{solucion_con_enlaces}")

            if faq_result.get("problem_identified"):
                mensajes.append(f"📋 FAQ:\n{faq_result['solution_content']}")

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


    # NUEVO MÉTODO: Procesar chunks guardando metadatos
    async def _procesar_chunks_con_metadatos(self, resultado_manual: Dict[str, Any]) -> str:
        """
        Procesa chunks para el LLM Y guarda metadatos para generar enlaces después
        """
        chunks_list = []
        self.chunks_metadata = {}  # Reset metadatos
        
        for item in resultado_manual['results']:
            try:
                chunks = await self.knowledge_base.get_chunk_with_context(item['chunk_id'])
                
                if not chunks:
                    continue
                
                # GUARDAR METADATOS para uso posterior
                self.chunks_metadata[item['chunk_id']] = {
                    'documento': item.get('documento', {}),
                    'equipo': item.get('equipo', {}),
                    'posicion': item.get('posicion', {}),
                    'similarity': item.get('similarity', 0),
                    'confidence': item.get('confidence', 0)
                }
                
                # FORMATO PARA EL LLM (tu formato existente)
                chunks_list.append({
                    'chunk_id': item['chunk_id'],
                    'page': item['documento']['pagina_numero'],
                    'text': (
                        chunks['chunk_anterior']['chunk_text'] + "\n" +
                        chunks['chunk_actual']['chunk_text'] + "\n" +
                        chunks['chunk_siguiente']['chunk_text']
                    )
                })
                
            except Exception as e:
                self.logger.error(f"Error procesando chunk {item.get('chunk_id', 'unknown')}: {e}")
                continue
        
        # RETORNAR STRING para el LLM (tu formato existente)
        return "\n\n".join(
            f"[{i+1}] (chunk_id {c['chunk_id']})\npágina {c['page']})\n{c['text']}"
            for i, c in enumerate(chunks_list)
        )

    # NUEVO MÉTODO: Generar solución final con enlaces
    async def _generar_solucion_con_enlaces(self, state: EroskiState, solution_content: str, chunk_id_list: List[str]) -> str:
        """
        Toma la solución del LLM y agrega enlaces de los chunks utilizados
        """
        if not chunk_id_list or not self.chunks_metadata:
            return solution_content
        
        # Generar enlaces para los chunks utilizados
        enlaces_chunks = []
        
        for chunk_id in chunk_id_list:
            if chunk_id in self.chunks_metadata:
                metadata = self.chunks_metadata[chunk_id]
                
                # Verificar si podemos generar enlaces
                if self._puede_generar_enlaces(metadata):
                    try:
                        print(f"🔍 DEBUG - Generando enlace para chunk {chunk_id}:")
                        print(f"   Documento: {metadata['documento']['filename']}")
                        print(f"   Página: {metadata['documento']['pagina_numero']}")
                        print(f"   Coordenadas: {metadata['posicion']}")
                        
                        enlaces = self.link_generator.generate_chunk_link(
                            documento_origen=metadata['documento']['filename'],
                            pagina_numero=metadata['documento']['pagina_numero'],
                            chunk_coordinates=metadata['posicion'],
                            chunk_id=chunk_id
                        )
                        
                        enlace_info = {
                            'chunk_id': chunk_id,
                            'page': metadata['documento']['pagina_numero'],
                            'documento': metadata['documento']['filename'],
                            'equipo': metadata['equipo'],
                            'enlaces': enlaces
                        }
                        
                        enlaces_chunks.append(enlace_info)
                        
                    except Exception as e:
                        self.logger.warning(f"Error generando enlace para chunk {chunk_id}: {e}")
        
        # Construir solución con enlaces
        solucion_final = solution_content
        
        if enlaces_chunks:
            # Verificar el canal para adaptar el formato
            is_whatsapp = state.get("channel") == "whatsapp"
            print(f"🔗 Generando enlaces - Canal: {state.get('channel')} - Es WhatsApp: {is_whatsapp}")
            
            if is_whatsapp:
                # Formato simple para WhatsApp
                solucion_final += "\n\n🔗 Referencias directas:\n"
                
                for enlace in enlaces_chunks:
                    equipo_info = ""
                    if enlace['equipo'].get('marca'):
                        equipo_info = f" ({enlace['equipo']['marca']} {enlace['equipo'].get('modelo', '')})"
                    
                    # Para WhatsApp: texto y URL separados claramente
                    #solucion_final += f"\n📄 Página {enlace['page']}{equipo_info}:\n"
                    #solucion_final += f"{enlace['enlaces']['pdf_link']}\n"
                    solucion_final += f"\n🖥️ Ver con resaltado:\n"
                    solucion_final += f"{enlace['enlaces']['web_viewer_link']}\n"
                
                solucion_final += "\n💡 Los enlaces con resaltado te llevan directo a la ubicación exacta."
            else:
                # Formato Markdown para Chainlit/Web
                solucion_final += "\n\n🔗 Referencias directas:\n"
                
                for enlace in enlaces_chunks:
                    equipo_info = ""
                    if enlace['equipo'].get('marca'):
                        equipo_info = f" ({enlace['equipo']['marca']} {enlace['equipo'].get('modelo', '')})"
                    
                    # Generar textos base
                    #texto_pdf = f"📄 Página {enlace['page']}{equipo_info}"
                    texto_pdf = f"📄 {equipo_info}"
                    texto_viewer = "🖥️ Ver con resaltado automático"
                    
                    # Aplicar el helper según canal (esto devuelve formato Markdown)
                    linea_pdf = renderizar_enlace(state, texto_pdf, enlace['enlaces']['pdf_link'])
                    linea_viewer = renderizar_enlace(state, texto_viewer, enlace['enlaces']['web_viewer_link'])
                    
                    # Agregar al mensaje final
                    #solucion_final += f"• {linea_pdf}\n• {linea_viewer}\n"
                    solucion_final += f"• Página: {enlace['page']} 👉 {linea_viewer}\n"
                
                solucion_final += f"• 📄 descargar manual {linea_pdf}\n\n💡 Tip: Los enlaces con resaltado te llevarán directamente a la ubicación exacta en el documento."
        
        return solucion_final

    # MÉTODO AUXILIAR: Verificar si podemos generar enlaces
    def _puede_generar_enlaces(self, metadata: Dict[str, Any]) -> bool:
        """
        Verifica si los metadatos contienen información suficiente para generar enlaces
        """
        try:
            # Verificar documento
            doc = metadata.get('documento', {})
            if not doc.get('filename') or not doc.get('pagina_numero'):
                return False
            
            # Verificar coordenadas
            pos = metadata.get('posicion', {})
            required_coords = ['x', 'y', 'width', 'height']
            
            if not all(coord in pos for coord in required_coords):
                return False
            
            # Verificar que las coordenadas sean válidas
            for coord in required_coords:
                if not isinstance(pos[coord], (int, float)) or pos[coord] < 0:
                    return False
            
            return True
            
        except Exception:
            return False

    # MANTENER TU MÉTODO ORIGINAL como fallback
    async def _procesar_chunks(self, resultado_manual: Dict[str, Any]) -> str:
        """
        Tu método original (mantenido para compatibilidad)
        """
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
#------------------------

    def _verificar_estructura_item(self, item: Dict[str, Any]) -> bool:
        """
        Verifica si un item tiene la estructura necesaria para generar enlaces con resaltado
        """
        try:
            # Verificar campos básicos requeridos
            if 'chunk_id' not in item:
                return False
            
            # Verificar documento
            if 'documento' not in item:
                return False
            
            doc = item['documento']
            if not isinstance(doc, dict):
                return False
                
            required_doc_fields = ['filename', 'pagina_numero']
            if not all(field in doc for field in required_doc_fields):
                return False
            
            # Verificar coordenadas (lo más importante para el resaltado)
            if 'posicion' not in item:
                return False
            
            pos = item['posicion']
            if not isinstance(pos, dict):
                return False
                
            required_coords = ['x', 'y', 'width', 'height']
            if not all(coord in pos for coord in required_coords):
                return False
            
            # Verificar que las coordenadas sean números válidos
            for coord in required_coords:
                if not isinstance(pos[coord], (int, float)) or pos[coord] < 0:
                    return False
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Error verificando estructura item: {e}")
            return False

    # 4. AGREGAR MÉTODO PARA FORMATO CON ENLACES:
    def _format_chunks_con_enlaces(self, chunks_list: List[Dict[str, Any]]) -> str:
        """
        Formatea chunks incluyendo enlaces de resaltado cuando están disponibles
        """
        if not chunks_list:
            return "No se encontraron chunks relevantes."
        
        formatted_parts = []
        
        for i, chunk in enumerate(chunks_list, 1):
            # Iniciar con tu formato base
            parte_chunk = f"[{i}] (chunk_id {chunk['chunk_id']})\npágina {chunk['page']})\n"
            
            # AGREGAR enlaces si están disponibles
            if chunk.get('enlaces') and not chunk['enlaces'].get('error'):
                enlaces_section = f"""
🔗 **Enlaces directos:**
• 📄 [Abrir PDF página {chunk['page']}]({chunk['enlaces']['pdf_link']})
• 🖥️ [Ver con resaltado automático]({chunk['enlaces']['web_viewer_link']})

"""
                parte_chunk += enlaces_section
            
            # Agregar el texto (tu formato existente)
            parte_chunk += chunk['text']
            
            # OPCIONAL: Información adicional si está disponible
            if chunk.get('similarity', 0) > 0:
                parte_chunk += f"\n\n📊 **Relevancia:** {chunk['similarity']:.1%}"
            
            if chunk.get('equipo') and chunk['equipo'].get('marca'):
                equipo_info = f" | **Equipo:** {chunk['equipo'].get('marca', '')} {chunk['equipo'].get('modelo', '')}"
                parte_chunk += equipo_info
            
            formatted_parts.append(parte_chunk)
        
        return "\n\n".join(formatted_parts)

    # 5. AGREGAR MÉTODO FALLBACK (tu formato original):
    def _format_chunks_original(self, chunks_list: List[Dict[str, Any]]) -> str:
        """
        Tu formato original para compatibilidad hacia atrás
        """
        return "\n\n".join(
            f"[{i+1}] (chunk_id {c['chunk_id']})\npágina {c['page']})\n{c['text']}"
            for i, c in enumerate(chunks_list)
        )

 