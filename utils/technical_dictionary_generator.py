# =====================================================
# utils/technical_dictionary_generator.py - Generador Automático de Diccionario Técnico
# =====================================================
"""
Sistema que genera y mantiene automáticamente el diccionario técnico de Eroski
a partir de manuales, consultas de usuarios y feedback del sistema.
"""

import asyncio
import asyncpg
import json
import re
import logging
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict, Counter
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
from dataclasses import dataclass

from config.settings import get_settings
from utils.llm.providers import get_llm, get_vectorizer

logger = logging.getLogger(__name__)

@dataclass
class TechnicalTerm:
    """Estructura de un término técnico"""
    term: str
    category: str
    confidence: float
    synonyms: List[str]
    related_terms: List[str]
    context_patterns: List[str]
    frequency: int
    last_updated: datetime
    sources: List[str]  # De dónde se extrajo
    user_validated: bool = False

class TechnicalDictionaryGenerator:
    """
    Genera automáticamente el diccionario técnico de Eroski mediante:
    1. Análisis de manuales existentes
    2. Extracción de terminología técnica con LLM
    3. Análisis de consultas de usuarios
    4. Aprendizaje de patrones de uso
    5. Validación automática y manual
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.llm = get_llm()
        self.vectorizer = get_vectorizer()
        self.dictionary: Dict[str, TechnicalTerm] = {}
        self.category_patterns = self._load_category_patterns()
        
    def _load_category_patterns(self) -> Dict[str, List[str]]:
        """Patrones iniciales para categorización automática"""
        return {
            "equipos": [
                r'\b(balanza|báscula|peso)\w*',
                r'\b(tpv|terminal|caja|registradora)\w*',
                r'\b(impresora|printer)\w*',
                r'\b(escáner|lector|scanner)\w*',
                r'\b(pantalla|display|monitor)\w*'
            ],
            "configuracion": [
                r'\b(config\w*|setup|ajust\w*|parámetr\w*)',
                r'\b(menú|menu|opciones)\w*',
                r'\b(configurar|establecer|definir)\w*'
            ],
            "problemas": [
                r'\b(error|fallo|problema|avería)\w*',
                r'\b(no\s+funciona|no\s+responde)',
                r'\b(atascado|bloqueado|colgado)\w*'
            ],
            "procedimientos": [
                r'\b(calibr\w*|manten\w*|limpie\w*)',
                r'\b(reiniciar|resetear|restaurar)\w*',
                r'\b(instalar|desinstalar|actualizar)\w*'
            ],
            "componentes": [
                r'\b(papel|rollo|tinta|cartucho)\w*',
                r'\b(cable|conector|puerto)\w*',
                r'\b(tecla|botón|sensor)\w*'
            ]
        }
    
    async def generate_complete_dictionary(self) -> Dict[str, TechnicalTerm]:
        """
        Proceso completo de generación del diccionario técnico
        """
        logger.info("🚀 Iniciando generación automática del diccionario técnico")
        
        try:
            # 1. Extraer términos de manuales existentes
            manual_terms = await self._extract_terms_from_manuals()
            logger.info(f"   📚 Extraídos {len(manual_terms)} términos de manuales")
            
            # 2. Analizar consultas históricas de usuarios
            user_terms = await self._extract_terms_from_user_queries()
            logger.info(f"   👥 Extraídos {len(user_terms)} términos de consultas")
            
            # 3. Generar sinónimos con LLM
            enhanced_terms = await self._enhance_terms_with_llm(manual_terms, user_terms)
            logger.info(f"   🤖 Mejorados {len(enhanced_terms)} términos con LLM")
            
            # 4. Detectar patrones automáticamente
            pattern_terms = await self._detect_usage_patterns(enhanced_terms)
            logger.info(f"   🔍 Detectados {len(pattern_terms)} patrones de uso")
            
            # 5. Validar y filtrar términos
            validated_terms = await self._validate_and_filter_terms(pattern_terms)
            logger.info(f"   ✅ Validados {len(validated_terms)} términos finales")
            
            # 6. Organizar en diccionario estructurado
            self.dictionary = self._organize_dictionary(validated_terms)
            
            # 7. Guardar diccionario
            await self._save_dictionary()
            
            logger.info("✅ Diccionario técnico generado exitosamente")
            return self.dictionary
            
        except Exception as e:
            logger.error(f"❌ Error generando diccionario: {e}")
            raise
    
    async def _extract_terms_from_manuals(self) -> List[Dict[str, Any]]:
        """Extrae términos técnicos de todos los manuales en la base de datos"""
        
        conn = await asyncpg.connect(self._build_connection_string())
        
        try:
            # Obtener todos los chunks de manuales
            chunks = await conn.fetch("""
                SELECT chunk_text, documento_origen, palabras_clave, chunk_metadata
                FROM knowledge_base
                WHERE LENGTH(chunk_text) > 50
                ORDER BY documento_origen, pagina_numero
            """)
            
            manual_terms = []
            
            # Procesar chunks en lotes para eficiencia
            for i in range(0, len(chunks), 10):
                batch = chunks[i:i+10]
                batch_terms = await self._extract_terms_from_chunk_batch(batch)
                manual_terms.extend(batch_terms)
                
                if i % 100 == 0:
                    logger.info(f"   📖 Procesados {i}/{len(chunks)} chunks")
            
            return manual_terms
            
        finally:
            await conn.close()
    
    async def _extract_terms_from_chunk_batch(self, chunks: List[Dict]) -> List[Dict[str, Any]]:
        """Extrae términos técnicos de un lote de chunks usando LLM"""
        
        # Preparar prompt para extracción de términos
        chunks_text = "\n---\n".join([chunk['chunk_text'] for chunk in chunks])
        
        extraction_prompt = f"""
Analiza el siguiente texto técnico de manuales de equipos de Eroski y extrae términos técnicos relevantes.

TEXTO A ANALIZAR:
{chunks_text}

INSTRUCCIONES:
1. Identifica términos técnicos específicos (nombres de equipos, procedimientos, componentes)
2. Clasifica cada término en una categoría
3. Sugiere sinónimos comunes para cada término
4. Indica el contexto de uso

FORMATO DE RESPUESTA (JSON):
{{
    "terminos_extraidos": [
        {{
            "termino": "balanza",
            "categoria": "equipos",
            "confianza": 0.95,
            "sinonimos": ["báscula", "peso", "pesa"],
            "contexto": "pesaje_productos",
            "ejemplos_uso": ["calibrar balanza", "balanza no funciona"]
        }}
    ]
}}

CATEGORÍAS VÁLIDAS: equipos, configuracion, problemas, procedimientos, componentes, estados, acciones

RESPUESTA (solo JSON válido):
"""
        
        try:
            # Llamar al LLM para extracción
            response = await self.llm.ainvoke(extraction_prompt)
            
            # Parsear respuesta JSON
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Limpiar respuesta para extraer JSON
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                extracted_data = json.loads(json_text)
                return extracted_data.get('terminos_extraidos', [])
            else:
                logger.warning("No se pudo extraer JSON válido de la respuesta del LLM")
                return []
                
        except Exception as e:
            logger.error(f"Error extrayendo términos con LLM: {e}")
            return []
    
    async def _extract_terms_from_user_queries(self) -> List[Dict[str, Any]]:
        """Extrae términos de consultas históricas de usuarios"""
        
        conn = await asyncpg.connect(self._build_connection_string())
        
        try:
            # Obtener consultas históricas de usuarios
            queries = await conn.fetch("""
                SELECT query_text, created_at, user_satisfied
                FROM rag_search_metrics
                WHERE created_at >= NOW() - INTERVAL '30 days'
                AND LENGTH(query_text) > 5
                ORDER BY created_at DESC
                LIMIT 1000
            """)
            
            if not queries:
                logger.info("   📊 No hay consultas históricas disponibles")
                return []
            
            # Agrupar consultas similares
            query_groups = self._group_similar_queries([q['query_text'] for q in queries])
            
            user_terms = []
            
            # Analizar cada grupo de consultas
            for group in query_groups:
                group_terms = await self._analyze_query_group(group)
                user_terms.extend(group_terms)
            
            return user_terms
            
        finally:
            await conn.close()
    
    def _group_similar_queries(self, queries: List[str]) -> List[List[str]]:
        """Agrupa consultas similares para análisis eficiente"""
        
        groups = []
        used_queries = set()
        
        for query in queries:
            if query in used_queries:
                continue
                
            # Encontrar consultas similares
            similar_group = [query]
            used_queries.add(query)
            
            for other_query in queries:
                if other_query in used_queries:
                    continue
                    
                # Calcular similitud simple por palabras comunes
                words1 = set(query.lower().split())
                words2 = set(other_query.lower().split())
                
                if len(words1) > 0 and len(words2) > 0:
                    similarity = len(words1.intersection(words2)) / len(words1.union(words2))
                    
                    if similarity > 0.4:  # Umbral de similitud
                        similar_group.append(other_query)
                        used_queries.add(other_query)
            
            if len(similar_group) >= 2:  # Solo grupos con múltiples consultas
                groups.append(similar_group)
        
        return groups
    
    async def _analyze_query_group(self, query_group: List[str]) -> List[Dict[str, Any]]:
        """Analiza un grupo de consultas similares para extraer términos"""
        
        group_text = "\n".join(query_group)
        
        analysis_prompt = f"""
Analiza las siguientes consultas de usuarios sobre equipos técnicos de Eroski.
Identifica términos técnicos y patrones de uso comunes.

CONSULTAS DE USUARIOS:
{group_text}

TAREAS:
1. Extraer términos técnicos mencionados por usuarios
2. Identificar sinónimos o variaciones que usan los usuarios
3. Detectar problemas o necesidades comunes
4. Clasificar por tipo de consulta

FORMATO DE RESPUESTA (JSON):
{{
    "terminos_usuario": [
        {{
            "termino": "balanza",
            "variaciones_usuario": ["bascula", "peso", "balanza digital"],
            "tipo_consulta": "problema",
            "frecuencia_estimada": 8,
            "contexto_tipico": "no_funciona"
        }}
    ]
}}

RESPUESTA (solo JSON válido):
"""
        
        try:
            response = await self.llm.ainvoke(analysis_prompt)
            
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                analyzed_data = json.loads(json_text)
                return analyzed_data.get('terminos_usuario', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error analizando grupo de consultas: {e}")
            return []
    
    async def _enhance_terms_with_llm(self, manual_terms: List[Dict], user_terms: List[Dict]) -> List[Dict[str, Any]]:
        """Mejora términos con sinónimos y relaciones usando LLM"""
        
        # Combinar términos de manuales y usuarios
        all_terms = manual_terms + user_terms
        
        # Agrupar por categorías para procesamiento eficiente
        terms_by_category = defaultdict(list)
        for term in all_terms:
            category = term.get('categoria', 'general')
            terms_by_category[category].append(term)
        
        enhanced_terms = []
        
        for category, category_terms in terms_by_category.items():
            logger.info(f"   🔧 Mejorando términos de categoría: {category}")
            
            # Procesar en lotes
            for i in range(0, len(category_terms), 20):
                batch = category_terms[i:i+20]
                enhanced_batch = await self._enhance_term_batch(batch, category)
                enhanced_terms.extend(enhanced_batch)
        
        return enhanced_terms
    
    async def _enhance_term_batch(self, terms_batch: List[Dict], category: str) -> List[Dict[str, Any]]:
        """Mejora un lote de términos con información adicional"""
        
        terms_list = [term.get('termino', '') for term in terms_batch]
        
        enhancement_prompt = f"""
Eres un experto en terminología técnica de equipos de tienda (balanzas, TPVs, impresoras).
Mejora la siguiente lista de términos técnicos de la categoría "{category}".

TÉRMINOS A MEJORAR:
{', '.join(terms_list)}

TAREAS:
1. Para cada término, generar sinónimos técnicos relevantes
2. Identificar términos relacionados en el contexto de Eroski
3. Sugerir patrones de contexto donde aparece el término
4. Indicar nivel de importancia técnica (0.0-1.0)

FORMATO DE RESPUESTA (JSON):
{{
    "terminos_mejorados": [
        {{
            "termino_original": "balanza",
            "termino_normalizado": "balanza",
            "sinonimos": ["báscula", "peso", "pesa", "balanza_digital"],
            "terminos_relacionados": ["calibración", "pesaje", "etiquetas", "tara"],
            "patrones_contexto": ["calibrar balanza", "balanza no funciona", "configurar balanza"],
            "importancia": 0.95,
            "categoria_refinada": "equipos_principales",
            "equipos_aplicables": ["DIBAL_Mistral", "DIBAL_Serie_500"]
        }}
    ]
}}

IMPORTANTE: 
- Usar solo sinónimos reales y técnicamente correctos
- Patrones de contexto basados en uso real en tiendas
- Términos relacionados deben ser relevantes para operaciones de tienda

RESPUESTA (solo JSON válido):
"""
        
        try:
            response = await self.llm.ainvoke(enhancement_prompt)
            
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                enhanced_data = json.loads(json_text)
                return enhanced_data.get('terminos_mejorados', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error mejorando términos: {e}")
            return []
    
    async def _detect_usage_patterns(self, enhanced_terms: List[Dict]) -> List[Dict[str, Any]]:
        """Detecta patrones de uso automáticamente desde consultas reales"""
        
        conn = await asyncpg.connect(self._build_connection_string())
        
        try:
            # Para cada término, buscar patrones de uso en consultas
            pattern_terms = []
            
            for term_data in enhanced_terms:
                term = term_data.get('termino_normalizado', term_data.get('termino_original', ''))
                
                # Buscar consultas que contengan este término
                usage_queries = await conn.fetch("""
                    SELECT query_text, user_satisfied, execution_time_ms
                    FROM rag_search_metrics
                    WHERE LOWER(query_text) LIKE %s
                    AND created_at >= NOW() - INTERVAL '60 days'
                    ORDER BY created_at DESC
                    LIMIT 50
                """, f'%{term.lower()}%')
                
                if usage_queries:
                    # Analizar patrones de uso
                    patterns = self._analyze_usage_patterns(term, usage_queries)
                    
                    # Enriquecer término con patrones reales
                    enriched_term = {
                        **term_data,
                        'patrones_uso_real': patterns['common_patterns'],
                        'tasa_exito': patterns['success_rate'],
                        'tiempo_respuesta_promedio': patterns['avg_response_time'],
                        'frecuencia_uso': len(usage_queries)
                    }
                    
                    pattern_terms.append(enriched_term)
                else:
                    # Término sin uso histórico, mantener sin patrones
                    pattern_terms.append(term_data)
            
            return pattern_terms
            
        finally:
            await conn.close()
    
    def _analyze_usage_patterns(self, term: str, usage_queries: List[Dict]) -> Dict[str, Any]:
        """Analiza patrones de uso real de un término"""
        
        patterns = {
            'common_patterns': [],
            'success_rate': 0.0,
            'avg_response_time': 0.0
        }
        
        # Extraer patrones comunes
        query_texts = [q['query_text'].lower() for q in usage_queries]
        
        # Buscar patrones frecuentes que incluyen el término
        pattern_counter = Counter()
        
        for query in query_texts:
            # Extraer contexto antes y después del término
            term_index = query.find(term.lower())
            if term_index != -1:
                # Palabras antes del término
                before_words = query[:term_index].strip().split()[-2:]
                # Palabras después del término  
                after_words = query[term_index + len(term):].strip().split()[:2]
                
                # Crear patrones
                if before_words:
                    pattern = f"{' '.join(before_words)} {term}"
                    pattern_counter[pattern] += 1
                
                if after_words:
                    pattern = f"{term} {' '.join(after_words)}"
                    pattern_counter[pattern] += 1
        
        # Obtener patrones más comunes
        patterns['common_patterns'] = [
            pattern for pattern, count in pattern_counter.most_common(5)
            if count >= 2  # Al menos 2 ocurrencias
        ]
        
        # Calcular métricas
        if usage_queries:
            satisfied_queries = [q for q in usage_queries if q.get('user_satisfied') is True]
            patterns['success_rate'] = len(satisfied_queries) / len(usage_queries)
            
            response_times = [q['execution_time_ms'] for q in usage_queries if q['execution_time_ms']]
            if response_times:
                patterns['avg_response_time'] = sum(response_times) / len(response_times)
        
        return patterns
    
    async def _validate_and_filter_terms(self, pattern_terms: List[Dict]) -> List[Dict[str, Any]]:
        """Valida y filtra términos para mantener solo los más relevantes"""
        
        validated_terms = []
        
        for term_data in pattern_terms:
            # Criterios de validación
            validation_score = 0.0
            
            # Factor 1: Importancia técnica (del LLM)
            importance = term_data.get('importancia', 0.5)
            validation_score += importance * 0.3
            
            # Factor 2: Frecuencia de uso real
            frequency = term_data.get('frecuencia_uso', 0)
            if frequency > 0:
                freq_score = min(frequency / 10.0, 1.0)  # Normalizar a [0,1]
                validation_score += freq_score * 0.3
            
            # Factor 3: Tasa de éxito en consultas
            success_rate = term_data.get('tasa_exito', 0.0)
            validation_score += success_rate * 0.2
            
            # Factor 4: Calidad de sinónimos
            synonyms = term_data.get('sinonimos', [])
            if len(synonyms) >= 2:
                validation_score += 0.1
            
            # Factor 5: Patrones de uso identificados
            patterns = term_data.get('patrones_uso_real', [])
            if len(patterns) >= 1:
                validation_score += 0.1
            
            # Filtrar términos con puntuación suficiente
            if validation_score >= 0.4:  # Umbral mínimo
                term_data['validation_score'] = validation_score
                validated_terms.append(term_data)
        
        # Ordenar por puntuación de validación
        validated_terms.sort(key=lambda x: x['validation_score'], reverse=True)
        
        logger.info(f"   🎯 Validación completada: {len(validated_terms)}/{len(pattern_terms)} términos aprobados")
        
        return validated_terms
    
    def _organize_dictionary(self, validated_terms: List[Dict]) -> Dict[str, TechnicalTerm]:
        """Organiza términos validados en diccionario estructurado"""
        
        dictionary = {}
        
        for term_data in validated_terms:
            term_key = term_data.get('termino_normalizado', term_data.get('termino_original', '')).lower()
            
            # Crear objeto TechnicalTerm
            tech_term = TechnicalTerm(
                term=term_key,
                category=term_data.get('categoria_refinada', term_data.get('categoria', 'general')),
                confidence=term_data.get('validation_score', 0.5),
                synonyms=term_data.get('sinonimos', []),
                related_terms=term_data.get('terminos_relacionados', []),
                context_patterns=term_data.get('patrones_uso_real', []),
                frequency=term_data.get('frecuencia_uso', 0),
                last_updated=datetime.now(),
                sources=['manual_analysis', 'user_queries', 'llm_enhancement'],
                user_validated=False
            )
            
            dictionary[term_key] = tech_term
            
            # Agregar sinónimos como entradas separadas que apuntan al término principal
            for synonym in tech_term.synonyms:
                if synonym.lower() != term_key:
                    dictionary[synonym.lower()] = tech_term
        
        return dictionary
    
    async def _save_dictionary(self):
        """Guarda el diccionario generado en archivos y base de datos"""
        
        # 1. Guardar como JSON para fácil lectura
        dict_data = {}
        for key, term in self.dictionary.items():
            if key == term.term:  # Solo términos principales, no sinónimos
                dict_data[key] = {
                    'term': term.term,
                    'category': term.category,
                    'confidence': term.confidence,
                    'synonyms': term.synonyms,
                    'related_terms': term.related_terms,
                    'context_patterns': term.context_patterns,
                    'frequency': term.frequency,
                    'last_updated': term.last_updated.isoformat(),
                    'sources': term.sources
                }
        
        # Guardar en archivo
        dict_path = Path("config/technical_dictionary_generated.json")
        dict_path.parent.mkdir(exist_ok=True)
        
        with open(dict_path, 'w', encoding='utf-8') as f:
            json.dump(dict_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"   💾 Diccionario guardado en: {dict_path}")
        
        # 2. Guardar en base de datos para uso en tiempo real
        await self._save_to_database()
    
    async def _save_to_database(self):
        """Guarda diccionario en base de datos para acceso rápido"""
        
        conn = await asyncpg.connect(self._build_connection_string())
        
        try:
            # Crear tabla si no existe
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS technical_dictionary (
                    id SERIAL PRIMARY KEY,
                    term VARCHAR(100) NOT NULL UNIQUE,
                    category VARCHAR(50) NOT NULL,
                    confidence FLOAT NOT NULL,
                    synonyms JSONB DEFAULT '[]',
                    related_terms JSONB DEFAULT '[]',
                    context_patterns JSONB DEFAULT '[]',
                    frequency INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sources JSONB DEFAULT '[]',
                    user_validated BOOLEAN DEFAULT FALSE
                );
            """)
            
            # Limpiar datos existentes
            await conn.execute("DELETE FROM technical_dictionary")
            
            # Insertar términos principales
            for key, term in self.dictionary.items():
                if key == term.term:  # Solo términos principales
                    await conn.execute("""
                        INSERT INTO technical_dictionary 
                        (term, category, confidence, synonyms, related_terms, context_patterns, 
                         frequency, last_updated, sources, user_validated)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """, 
                    term.term,
                    term.category,
                    term.confidence,
                    json.dumps(term.synonyms),
                    json.dumps(term.related_terms),
                    json.dumps(term.context_patterns),
                    term.frequency,
                    term.last_updated,
                    json.dumps(term.sources),
                    term.user_validated
                    )
            
            # Crear índices para búsqueda rápida
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tech_dict_term ON technical_dictionary(term);
                CREATE INDEX IF NOT EXISTS idx_tech_dict_category ON technical_dictionary(category);
                CREATE INDEX IF NOT EXISTS idx_tech_dict_confidence ON technical_dictionary(confidence DESC);
            """)
            
            logger.info("   💾 Diccionario guardado en base de datos")
            
        finally:
            await conn.close()
    
    def _build_connection_string(self) -> str:
        """Construye string de conexión a la base de datos"""
        conn_params = {
            'host': self.settings.database.host,
            'port': self.settings.database.port,
            'database': self.settings.database.name,
            'user': self.settings.database.user,
        }
        
        if self.settings.database.password:
            conn_params['password'] = self.settings.database.password
        
        return f"postgresql://{conn_params['user']}{':%s' % conn_params.get('password', '') if conn_params.get('password') else ''}@{conn_params['host']}:{conn_params['port']}/{conn_params['database']}"

class DynamicTechnicalQueryExpander:
    """
    Expansor de consultas que usa el diccionario técnico generado dinámicamente
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.dictionary_cache = {}
        self.cache_expiry = None
        self.cache_duration = timedelta(hours=6)  # Actualizar cache cada 6 horas
    
    async def expand_query(self, query: str) -> List[str]:
        """
        Expande consulta usando diccionario técnico dinámico
        """
        # Actualizar cache si es necesario
        await self._update_cache_if_needed()
        
        # Limpiar y normalizar consulta
        clean_query = re.sub(r'[^\w\s]', ' ', query.lower())
        clean_query = ' '.join(clean_query.split())
        
        queries = [query, clean_query]  # Original + limpia
        
        # Expandir usando diccionario técnico
        expanded_terms = set()
        
        for word in clean_query.split():
            if word in self.dictionary_cache:
                term_data = self.dictionary_cache[word]
                
                # Agregar sinónimos
                expanded_terms.update(term_data.get('synonyms', []))
                
                # Agregar términos relacionados (con menor peso)
                related = term_data.get('related_terms', [])
                expanded_terms.update(related[:3])  # Solo los 3 más relevantes
        
        # Crear consulta expandida
        if expanded_terms:
            expanded_query = f"{clean_query} {' '.join(expanded_terms)}"
            queries.append(expanded_query)
        
        # Agregar patrones de contexto específicos
        context_queries = await self._generate_context_queries(clean_query)
        queries.extend(context_queries)
        
        # Eliminar duplicados y limitar
        unique_queries = list(dict.fromkeys(queries))  # Preserva orden
        return unique_queries[:5]  # Máximo 5 consultas
    
    async def _update_cache_if_needed(self):
        """Actualiza cache del diccionario técnico si es necesario"""
        
        current_time = datetime.now()
        
        if (not self.dictionary_cache or 
            not self.cache_expiry or 
            current_time > self.cache_expiry):
            
            await self._load_dictionary_from_database()
            self.cache_expiry = current_time + self.cache_duration
    
    async def _load_dictionary_from_database(self):
        """Carga diccionario técnico desde base de datos"""
        
        conn = await asyncpg.connect(self._build_connection_string())
        
        try:
            # Cargar términos con alta confianza
            terms = await conn.fetch("""
                SELECT term, category, synonyms, related_terms, context_patterns, confidence
                FROM technical_dictionary
                WHERE confidence >= 0.4
                ORDER BY confidence DESC, frequency DESC
            """)
            
            self.dictionary_cache = {}
            
            for term_row in terms:
                term_key = term_row['term']
                
                term_data = {
                    'category': term_row['category'],
                    'synonyms': json.loads(term_row['synonyms']) if term_row['synonyms'] else [],
                    'related_terms': json.loads(term_row['related_terms']) if term_row['related_terms'] else [],
                    'context_patterns': json.loads(term_row['context_patterns']) if term_row['context_patterns'] else [],
                    'confidence': term_row['confidence']
                }
                
                # Agregar término principal
                self.dictionary_cache[term_key] = term_data
                
                # Agregar sinónimos que apuntan al mismo término
                for synonym in term_data['synonyms']:
                    self.dictionary_cache[synonym.lower()] = term_data
            
            logger.info(f"   📚 Diccionario técnico cargado: {len(terms)} términos principales")
            
        except Exception as e:
            logger.error(f"Error cargando diccionario técnico: {e}")
            # Usar diccionario básico como fallback
            self.dictionary_cache = self._get_fallback_dictionary()
            
        finally:
            await conn.close()
    
    def _get_fallback_dictionary(self) -> Dict[str, Any]:
        """Diccionario básico como fallback si falla la carga dinámica"""
        return {
            'balanza': {
                'synonyms': ['báscula', 'peso', 'pesa', 'dibal'],
                'related_terms': ['calibración', 'pesaje', 'etiquetas'],
                'category': 'equipos'
            },
            'configuracion': {
                'synonyms': ['config', 'setup', 'ajustes', 'parámetros'],
                'related_terms': ['menú', 'opciones', 'configurar'],
                'category': 'procedimientos'
            },
            'retroiluminacion': {
                'synonyms': ['backlight', 'brillo', 'iluminación', 'luz'],
                'related_terms': ['pantalla', 'display', 'monitor'],
                'category': 'configuracion'
            }
        }
    
    async def _generate_context_queries(self, query: str) -> List[str]:
        """Genera consultas de contexto específicas"""
        
        context_queries = []
        
        # Detectar intenciones comunes
        if any(word in query for word in ['como', 'cómo']):
            context_queries.append(f"procedimiento {query.replace('como', '').replace('cómo', '').strip()}")
        
        if any(word in query for word in ['problema', 'error', 'no funciona']):
            context_queries.append(f"solucion {query}")
            context_queries.append(f"diagnostico {query}")
        
        if any(word in query for word in ['configurar', 'ajustar', 'setup']):
            context_queries.append(f"menu configuracion {query}")
        
        return context_queries
    
    def _build_connection_string(self) -> str:
        """Construye string de conexión"""
        conn_params = {
            'host': self.settings.database.host,
            'port': self.settings.database.port,
            'database': self.settings.database.name,
            'user': self.settings.database.user,
        }
        
        if self.settings.database.password:
            conn_params['password'] = self.settings.database.password
        
        return f"postgresql://{conn_params['user']}{':%s' % conn_params.get('password', '') if conn_params.get('password') else ''}@{conn_params['host']}:{conn_params['port']}/{conn_params['database']}"

# =====================================================
# Script de generación automática del diccionario
# =====================================================

async def generate_technical_dictionary():
    """Función principal para generar el diccionario técnico"""
    
    print("🚀 GENERADOR AUTOMÁTICO DE DICCIONARIO TÉCNICO EROSKI")
    print("=" * 60)
    
    generator = TechnicalDictionaryGenerator()
    
    try:
        # Generar diccionario completo
        dictionary = await generator.generate_complete_dictionary()
        
        print(f"\n✅ DICCIONARIO GENERADO EXITOSAMENTE")
        print(f"📊 Total términos: {len([k for k, v in dictionary.items() if k == v.term])}")
        print(f"📊 Total sinónimos: {len(dictionary) - len([k for k, v in dictionary.items() if k == v.term])}")
        
        # Mostrar estadísticas por categoría
        categories = {}
        for term in dictionary.values():
            if term.term in dictionary:  # Solo términos principales
                cat = term.category
                categories[cat] = categories.get(cat, 0) + 1
        
        print(f"\n📋 DISTRIBUCIÓN POR CATEGORÍAS:")
        for category, count in sorted(categories.items()):
            print(f"   • {category}: {count} términos")
        
        print(f"\n📁 ARCHIVOS GENERADOS:")
        print(f"   📄 config/technical_dictionary_generated.json")
        print(f"   🗄️ Tabla: technical_dictionary (PostgreSQL)")
        
        print(f"\n🔧 USO EN EL CÓDIGO:")
        print(f"   # El TechnicalQueryExpander ahora usará automáticamente")
        print(f"   # el diccionario generado para expansión de consultas")
        
        return dictionary
        
    except Exception as e:
        print(f"\n❌ ERROR EN GENERACIÓN: {e}")
        raise


class DictionaryMaintenanceScheduler:
    """
    Programador que actualiza automáticamente el diccionario técnico
    """
    
    def __init__(self):
        self.generator = TechnicalDictionaryGenerator()
        self.last_update = None
        self.update_interval = timedelta(days=7)  # Actualizar semanalmente
    
    async def check_and_update_if_needed(self):
        """Verifica si es necesario actualizar el diccionario"""
        
        current_time = datetime.now()
        
        # Verificar si es tiempo de actualizar
        if (not self.last_update or 
            current_time - self.last_update > self.update_interval):
            
            logger.info("🔄 Iniciando actualización automática del diccionario técnico")
            
            try:
                # Generar diccionario actualizado
                new_dictionary = await self.generator.generate_complete_dictionary()
                
                # Marcar como actualizado
                self.last_update = current_time
                
                logger.info("✅ Diccionario técnico actualizado automáticamente")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Error en actualización automática: {e}")
                return False
        
        return False
    
    async def force_update(self):
        """Fuerza actualización inmediata del diccionario"""
        
        logger.info("🔧 Forzando actualización del diccionario técnico")
        
        try:
            new_dictionary = await self.generator.generate_complete_dictionary()
            self.last_update = datetime.now()
            
            logger.info("✅ Actualización forzada completada")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en actualización forzada: {e}")
            return False


if __name__ == "__main__":
    asyncio.run(generate_technical_dictionary())