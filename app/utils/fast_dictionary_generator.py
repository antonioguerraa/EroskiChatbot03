# =====================================================
# fast_dictionary_generator.py - Generador con cache y modo test
# =====================================================
"""
Generador de diccionario técnico optimizado con:
- Modo test (pocos chunks)
- Guardado temporal para evitar re-procesar
- Verificación de tablas antes de ejecutar
- Cache de resultados LLM
"""

import asyncio
import asyncpg
import json
import re
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import sys
import pickle

# Agregar el directorio raíz al path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import get_settings
from app.utils.llm.providers import get_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FastTechnicalDictionary:
    """Generador rápido con cache y modo test"""
    
    def __init__(self, test_mode: bool = False, max_chunks: int = 50):
        self.settings = get_settings()
        self.llm = get_llm()
        self.test_mode = test_mode
        self.max_chunks = max_chunks
        self.cache_dir = Path("data/dictionary_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_connection_string(self) -> str:
        """Construye string de conexión"""
        return f"postgresql://{self.settings.database.user}:{self.settings.database.password or ''}@{self.settings.database.host}:{self.settings.database.port}/{self.settings.database.name}"
    
    async def verify_database_tables(self) -> bool:
        """Verifica que todas las tablas necesarias existen"""
        print("🔍 Verificando tablas de base de datos...")
        
        try:
            conn = await asyncpg.connect(self._get_connection_string())
            
            try:
                # Verificar tablas requeridas
                required_tables = ['knowledge_base', 'rag_search_metrics']
                existing_tables = []
                missing_tables = []
                
                for table in required_tables:
                    exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' AND table_name = $1
                        )
                    """, table)
                    
                    if exists:
                        existing_tables.append(table)
                        print(f"   ✅ {table}")
                    else:
                        missing_tables.append(table)
                        print(f"   ❌ {table} - FALTA")
                
                if missing_tables:
                    print(f"\n⚠️ TABLAS FALTANTES: {missing_tables}")
                    print("💡 Ejecuta: python -c \"import asyncpg; # crear tabla...\"")
                    return False
                
                print("✅ Todas las tablas requeridas existen")
                return True
                
            finally:
                await conn.close()
                
        except Exception as e:
            print(f"❌ Error verificando tablas: {e}")
            return False
    
    async def create_missing_tables(self):
        """Crea tablas faltantes automáticamente"""
        print("🔧 Creando tablas faltantes...")
        
        conn = await asyncpg.connect(self._get_connection_string())
        
        try:
            # Crear tabla rag_search_metrics
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_search_metrics (
                    id SERIAL PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    search_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    results_found INTEGER DEFAULT 0,
                    user_feedback VARCHAR(50),
                    confidence_score DECIMAL(3,2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Crear índices
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rag_metrics_query ON rag_search_metrics(query_text);
                CREATE INDEX IF NOT EXISTS idx_rag_metrics_timestamp ON rag_search_metrics(search_timestamp);
            """)
            
            # Insertar datos de ejemplo
            await conn.execute("""
                INSERT INTO rag_search_metrics (query_text, results_found, confidence_score) 
                VALUES 
                ('calibrar balanza', 5, 0.85),
                ('error impresora', 3, 0.72),
                ('configurar tpv', 4, 0.91)
                ON CONFLICT DO NOTHING;
            """)
            
            print("✅ Tablas creadas exitosamente")
            
        finally:
            await conn.close()
    
    def _get_cache_file(self, stage: str) -> Path:
        """Obtiene ruta de archivo de cache para una etapa"""
        return self.cache_dir / f"{stage}_cache.pkl"
    
    def _save_cache(self, stage: str, data: Any):
        """Guarda datos en cache"""
        cache_file = self._get_cache_file(stage)
        with open(cache_file, 'wb') as f:
            pickle.dump({
                'data': data,
                'timestamp': datetime.now(),
                'test_mode': self.test_mode,
                'max_chunks': self.max_chunks
            }, f)
        print(f"💾 Cache guardado: {cache_file}")
    
    def _load_cache(self, stage: str) -> Optional[Any]:
        """Carga datos desde cache si existe"""
        cache_file = self._get_cache_file(stage)
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            
            # Verificar que el cache es compatible
            cache_age = datetime.now() - cache_data['timestamp']
            if cache_age.days > 1:  # Cache válido por 1 día
                print(f"⚠️ Cache {stage} expirado ({cache_age.days} días)")
                return None
            
            if cache_data.get('test_mode') != self.test_mode:
                print(f"⚠️ Cache {stage} de modo diferente")
                return None
            
            print(f"📁 Cargando cache: {stage}")
            return cache_data['data']
            
        except Exception as e:
            print(f"⚠️ Error cargando cache {stage}: {e}")
            return None
    
    async def extract_terms_from_manuals(self) -> List[Dict]:
        """Extrae términos de manuales con cache"""
        
        # Intentar cargar desde cache
        cached_terms = self._load_cache('manual_terms')
        if cached_terms:
            print(f"📁 Términos de manual cargados desde cache: {len(cached_terms)}")
            return cached_terms
        
        print("📚 Extrayendo términos de manuales...")
        
        conn = await asyncpg.connect(self._get_connection_string())
        
        try:
            # Obtener chunks (limitados en modo test)
            if self.test_mode:
                print(f"🧪 MODO TEST: Procesando solo {self.max_chunks} chunks")
                chunks = await conn.fetch("""
                    SELECT chunk_text, pagina_numero, seccion, palabras_clave
                    FROM knowledge_base 
                    WHERE LENGTH(chunk_text) > 100
                    ORDER BY pagina_numero
                    LIMIT $1
                """, self.max_chunks)
            else:
                chunks = await conn.fetch("""
                    SELECT chunk_text, pagina_numero, seccion, palabras_clave
                    FROM knowledge_base 
                    WHERE LENGTH(chunk_text) > 100
                    ORDER BY pagina_numero
                """)
            
            print(f"📊 Procesando {len(chunks)} chunks...")
            
            all_terms = []
            batch_size = 10  # Procesar en lotes de 10
            
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                print(f"🔄 Procesando lote {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
                
                batch_terms = await self._process_chunk_batch(batch)
                all_terms.extend(batch_terms)
                
                # Guardar cache parcial cada 50 chunks
                if i > 0 and i % 50 == 0:
                    self._save_cache('manual_terms_partial', all_terms)
            
            # Guardar cache final
            self._save_cache('manual_terms', all_terms)
            
            print(f"✅ Extraídos {len(all_terms)} términos de manuales")
            return all_terms
            
        finally:
            await conn.close()
    
    async def _process_chunk_batch(self, chunks: List) -> List[Dict]:
        """Procesa un lote de chunks con LLM"""
        
        batch_text = ""
        for chunk in chunks:
            chunk_preview = chunk['chunk_text'][:200] + "..." if len(chunk['chunk_text']) > 200 else chunk['chunk_text']
            batch_text += f"CHUNK: {chunk_preview}\n\n"
        
        prompt = f"""
Extrae términos técnicos específicos de estos chunks de un manual de balanza DIBAL Mistral.

CHUNKS:
{batch_text}

INSTRUCCIONES:
- Solo términos técnicos relevantes para balanzas, TPV, impresoras
- Incluir códigos de error, procedimientos, componentes
- Categorizar cada término
- Formato JSON ESTRICTO

FORMATO RESPUESTA:
{{"terms": [
  {{"term": "calibrar", "category": "procedimientos", "confidence": 0.9}},
  {{"term": "tara", "category": "componentes", "confidence": 0.8}}
]}}

RESPUESTA:
"""
        
        try:
            response = await self.llm.ainvoke(prompt)
            
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Extraer JSON
            json_match = re.search(r'\{"terms":\s*\[(.*?)\]\s*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    json_data = json.loads(json_match.group())
                    return json_data.get('terms', [])
                except json.JSONDecodeError:
                    pass
            
            # Fallback: extraer términos básicos
            return self._extract_basic_terms_from_chunks(chunks)
            
        except Exception as e:
            logger.warning(f"Error procesando lote con LLM: {e}")
            return self._extract_basic_terms_from_chunks(chunks)
    
    def _extract_basic_terms_from_chunks(self, chunks: List) -> List[Dict]:
        """Extracción básica sin LLM como fallback"""
        
        basic_terms = []
        
        for chunk in chunks:
            # Usar palabras clave existentes
            if chunk.get('palabras_clave'):
                for keyword in chunk['palabras_clave']:
                    if keyword and len(keyword) > 2:
                        basic_terms.append({
                            'term': keyword.lower().strip(),
                            'category': 'general',
                            'confidence': 0.5
                        })
            
            # Buscar patrones conocidos
            text = chunk['chunk_text'].lower()
            
            # Términos de balanza
            balanza_patterns = [
                r'\b(calibr\w*)', r'\b(tara)', r'\b(peso)', r'\b(balanza)',
                r'\b(dibal)', r'\b(mistral)', r'\b(error\s*\d+)'
            ]
            
            for pattern in balanza_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    basic_terms.append({
                        'term': match.strip(),
                        'category': 'equipos',
                        'confidence': 0.7
                    })
        
        return basic_terms[:50]  # Limitar resultados
    
    async def generate_dictionary(self) -> Dict[str, Any]:
        """Genera diccionario completo con optimizaciones"""
        
        print("🚀 GENERADOR RÁPIDO DE DICCIONARIO TÉCNICO")
        print("=" * 50)
        
        if self.test_mode:
            print(f"🧪 MODO TEST ACTIVADO - Max {self.max_chunks} chunks")
        
        try:
            # 1. Verificar base de datos
            if not await self.verify_database_tables():
                print("🔧 Creando tablas faltantes...")
                await self.create_missing_tables()
            
            # 2. Extraer términos de manuales
            manual_terms = await self.extract_terms_from_manuals()
            
            # 3. Procesar y organizar términos
            print("🔄 Organizando diccionario...")
            dictionary = self._organize_terms(manual_terms)
            
            # 4. Guardar resultado
            await self._save_dictionary(dictionary)
            
            return dictionary
            
        except Exception as e:
            print(f"❌ Error: {e}")
            raise
    
    def _organize_terms(self, terms: List[Dict]) -> Dict[str, Any]:
        """Organiza términos en diccionario estructurado"""
        
        dictionary = {}
        
        # Contar frecuencias
        term_counts = {}
        for term_data in terms:
            term = term_data['term']
            term_counts[term] = term_counts.get(term, 0) + 1
        
        # Filtrar por frecuencia mínima
        min_frequency = 2 if not self.test_mode else 1
        
        for term_data in terms:
            term = term_data['term']
            
            if term_counts[term] >= min_frequency and len(term) > 2:
                dictionary[term] = {
                    'term': term,
                    'category': term_data.get('category', 'general'),
                    'confidence': min(term_data.get('confidence', 0.5) * (term_counts[term] / 5), 1.0),
                    'frequency': term_counts[term],
                    'synonyms': [],
                    'related_terms': [],
                    'last_updated': datetime.now().isoformat(),
                    'source': 'fast_extraction'
                }
        
        return dictionary
    
    async def _save_dictionary(self, dictionary: Dict[str, Any]):
        """Guarda diccionario en archivo"""
        
        # Crear directorio
        config_dir = Path("config")
        config_dir.mkdir(exist_ok=True)
        
        # Nombre de archivo según modo
        filename = "technical_dictionary_test.json" if self.test_mode else "technical_dictionary_fast.json"
        dict_file = config_dir / filename
        
        # Guardar
        with open(dict_file, 'w', encoding='utf-8') as f:
            json.dump(dictionary, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Diccionario guardado: {dict_file}")
        
        # Estadísticas
        categories = {}
        for term_data in dictionary.values():
            cat = term_data['category']
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"\n📊 ESTADÍSTICAS:")
        print(f"   📄 Total términos: {len(dictionary)}")
        
        for category, count in sorted(categories.items()):
            print(f"   📋 {category}: {count} términos")

async def main():
    """Script principal con opciones"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Generador rápido de diccionario técnico")
    parser.add_argument("--test", action="store_true", help="Modo test (pocos chunks)")
    parser.add_argument("--max-chunks", type=int, default=20, help="Max chunks en modo test")
    parser.add_argument("--clear-cache", action="store_true", help="Limpiar cache")
    
    args = parser.parse_args()
    
    if args.clear_cache:
        cache_dir = Path("data/dictionary_cache")
        if cache_dir.exists():
            import shutil
            shutil.rmtree(cache_dir)
            print("🗑️ Cache limpiado")
    
    # Crear generador
    generator = FastTechnicalDictionary(
        test_mode=args.test,
        max_chunks=args.max_chunks
    )
    
    # Generar diccionario
    dictionary = await generator.generate_dictionary()
    
    print("\n✅ DICCIONARIO GENERADO EXITOSAMENTE")
    print("\n🚀 PRÓXIMOS PASOS:")
    print("1. 🧪 Probar búsqueda: python database/scripts/test_vector_search.py")
    print("2. 🤖 Ejecutar chatbot: python main.py")

if __name__ == "__main__":
    asyncio.run(main())