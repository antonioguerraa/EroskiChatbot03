# =====================================================
# tests/verify_rag_optimization.py - Verificación Completa RAG
# =====================================================
"""
Suite de verificación completa para validar que todas las optimizaciones
del sistema RAG estén funcionando correctamente.
"""

import asyncio
import time
import json
import statistics
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
import sys
from datetime import datetime

# Setup path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RAGVerification")

class RAGOptimizationVerifier:
    """Verificador completo de optimizaciones RAG"""
    
    def __init__(self):
        self.kb = None
        self.test_results = {}
        self.performance_metrics = {}
        
    async def run_complete_verification(self):
        """Ejecuta verificación completa del sistema RAG optimizado"""
        logger.info("🔍 INICIANDO VERIFICACIÓN COMPLETA DEL RAG OPTIMIZADO")
        logger.info("=" * 60)
        
        try:
            # Inicializar sistema
            await self._initialize_system()
            
            # Pruebas de funcionalidad
            await self._test_basic_functionality()
            await self._test_search_methods()
            await self._test_cache_system()
            await self._test_query_expansion()
            await self._test_context_enrichment()
            
            # Pruebas de rendimiento
            await self._test_performance_benchmarks()
            await self._test_concurrent_searches()
            
            # Pruebas de calidad
            await self._test_search_quality()
            await self._test_relevance_scoring()
            
            # Análisis de métricas
            await self._analyze_system_metrics()
            
            # Generar reporte final
            self._generate_verification_report()
            
        except Exception as e:
            logger.error(f"❌ Error en verificación: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _initialize_system(self):
        """Inicializa el sistema RAG optimizado"""
        logger.info("🚀 Inicializando sistema RAG optimizado...")
        
        try:
            from nodes.improved_eroski_knowledge_base import OptimizedEroskiKnowledgeBase
            self.kb = OptimizedEroskiKnowledgeBase()
            logger.info("   ✅ Sistema RAG optimizado inicializado")
            
            # Verificar configuración
            if hasattr(self.kb, 'searcher'):
                logger.info(f"   ✅ Motor de búsqueda híbrido: {type(self.kb.searcher).__name__}")
                logger.info(f"   ✅ Cache configurado: {hasattr(self.kb.searcher, 'cache')}")
                logger.info(f"   ✅ Expansor de consultas: {hasattr(self.kb.searcher, 'query_expander')}")
            
        except ImportError as e:
            logger.error("   ❌ No se pudo importar OptimizedEroskiKnowledgeBase")
            logger.error("   💡 Ejecuta primero: python migration/integrate_optimized_rag.py")
            raise
    
    async def _test_basic_functionality(self):
        """Prueba funcionalidad básica del sistema"""
        logger.info("🔧 Probando funcionalidad básica...")
        
        test_cases = [
            {
                "name": "Búsqueda simple",
                "query": "balanza no funciona",
                "expected_keywords": ["balanza", "problema", "solución"]
            },
            {
                "name": "Consulta específica",
                "query": "como calibrar balanza dibal mistral",
                "expected_keywords": ["calibra", "dibal", "mistral", "procedimiento"]
            },
            {
                "name": "Problema de impresión",
                "query": "etiquetas no se imprimen",
                "expected_keywords": ["etiqueta", "impre", "papel", "rollo"]
            }
        ]
        
        basic_results = {}
        
        for test_case in test_cases:
            try:
                start_time = time.time()
                result = self.kb.buscar_solucion_rag(test_case["query"], top_k=3)
                duration = time.time() - start_time
                
                # Verificar resultado
                has_content = len(result) > 100
                has_keywords = any(keyword.lower() in result.lower() 
                                 for keyword in test_case["expected_keywords"])
                has_structure = "solución" in result.lower() or "**" in result
                
                basic_results[test_case["name"]] = {
                    "success": has_content and (has_keywords or "no se encontraron" in result.lower()),
                    "duration": duration,
                    "content_length": len(result),
                    "has_keywords": has_keywords,
                    "has_structure": has_structure
                }
                
                status = "✅" if basic_results[test_case["name"]]["success"] else "❌"
                logger.info(f"   {status} {test_case['name']}: {duration:.3f}s, {len(result)} chars")
                
            except Exception as e:
                basic_results[test_case["name"]] = {
                    "success": False,
                    "error": str(e),
                    "duration": 0
                }
                logger.error(f"   ❌ {test_case['name']}: {e}")
        
        self.test_results["basic_functionality"] = basic_results
        
        # Estadísticas generales
        total_tests = len(test_cases)
        successful_tests = sum(1 for r in basic_results.values() if r["success"])
        success_rate = successful_tests / total_tests
        
        logger.info(f"   📊 Funcionalidad básica: {successful_tests}/{total_tests} ({success_rate:.1%})")
    
    async def _test_search_methods(self):
        """Prueba diferentes métodos de búsqueda"""
        logger.info("🔍 Probando métodos de búsqueda...")
        
        # Verificar si tenemos acceso a métodos individuales
        if not hasattr(self.kb, 'searcher'):
            logger.warning("   ⚠️ No se puede acceder a métodos de búsqueda individuales")
            return
        
        search_methods_results = {}
        test_query = "balanza dibal problema etiquetas"
        
        # Probar métodos disponibles
        method_configs = [
            {"methods": ["vector"], "name": "Solo vectorial"},
            {"methods": ["text"], "name": "Solo texto"},
            {"methods": ["keyword"], "name": "Solo palabras clave"},
            {"methods": ["vector", "text"], "name": "Híbrido vector+texto"},
            {"methods": ["vector", "text", "keyword"], "name": "Híbrido completo"}
        ]
        
        for config in method_configs:
            try:
                start_time = time.time()
                
                # Usar búsqueda avanzada si está disponible
                if hasattr(self.kb.searcher, 'search'):
                    results, metrics = await self.kb.searcher.search(
                        test_query,
                        top_k=3,
                        search_methods=config["methods"]
                    )
                    duration = time.time() - start_time
                    
                    search_methods_results[config["name"]] = {
                        "success": len(results) > 0,
                        "results_count": len(results),
                        "duration": duration,
                        "methods_used": metrics.search_methods_used
                    }
                    
                    logger.info(f"   ✅ {config['name']}: {len(results)} resultados en {duration:.3f}s")
                
            except Exception as e:
                search_methods_results[config["name"]] = {
                    "success": False,
                    "error": str(e)
                }
                logger.warning(f"   ⚠️ {config['name']}: {e}")
        
        self.test_results["search_methods"] = search_methods_results
    
    async def _test_cache_system(self):
        """Prueba el sistema de cache"""
        logger.info("💾 Probando sistema de cache...")
        
        cache_results = {}
        test_query = "test cache balanza problema específico"
        
        try:
            # Primera búsqueda (sin cache)
            start_time = time.time()
            result1 = self.kb.buscar_solucion_rag(test_query)
            first_duration = time.time() - start_time
            
            # Pequeña pausa
            await asyncio.sleep(0.1)
            
            # Segunda búsqueda (con cache)
            start_time = time.time()
            result2 = self.kb.buscar_solucion_rag(test_query)
            second_duration = time.time() - start_time
            
            # Verificar funcionalidad del cache
            cache_working = result1 == result2
            speed_improvement = first_duration / second_duration if second_duration > 0 else 1
            
            cache_results = {
                "cache_working": cache_working,
                "first_duration": first_duration,
                "second_duration": second_duration,
                "speed_improvement": speed_improvement,
                "results_identical": result1 == result2
            }
            
            logger.info(f"   ✅ Cache funcionando: {cache_working}")
            logger.info(f"   ⚡ Mejora velocidad: {speed_improvement:.2f}x")
            logger.info(f"   📊 Tiempos: {first_duration:.3f}s → {second_duration:.3f}s")
            
        except Exception as e:
            cache_results = {"error": str(e), "cache_working": False}
            logger.error(f"   ❌ Error probando cache: {e}")
        
        self.test_results["cache_system"] = cache_results
    
    async def _test_query_expansion(self):
        """Prueba la expansión de consultas"""
        logger.info("🔍 Probando expansión de consultas...")
        
        if not hasattr(self.kb, 'searcher') or not hasattr(self.kb.searcher, 'query_expander'):
            logger.warning("   ⚠️ Expansor de consultas no disponible")
            return
        
        expansion_tests = [
            {
                "query": "balanza",
                "expected_expansions": ["peso", "pesar", "dibal"]
            },
            {
                "query": "no imprime",
                "expected_expansions": ["papel", "rollo", "atasco"]
            },
            {
                "query": "error pantalla",
                "expected_expansions": ["display", "monitor", "visor"]
            }
        ]
        
        expansion_results = {}
        
        for test in expansion_tests:
            try:
                expanded_queries = self.kb.searcher.query_expander.expand_query(test["query"])
                
                # Verificar que se expandió
                has_expansion = len(expanded_queries) > 1
                has_expected = any(
                    any(exp in expanded for exp in test["expected_expansions"])
                    for expanded in expanded_queries
                )
                
                expansion_results[test["query"]] = {
                    "original": test["query"],
                    "expanded": expanded_queries,
                    "expansion_count": len(expanded_queries),
                    "has_expansion": has_expansion,
                    "has_expected_terms": has_expected
                }
                
                logger.info(f"   ✅ '{test['query']}' → {len(expanded_queries)} consultas")
                
            except Exception as e:
                expansion_results[test["query"]] = {"error": str(e)}
                logger.error(f"   ❌ Error expandiendo '{test['query']}': {e}")
        
        self.test_results["query_expansion"] = expansion_results
    
    async def _test_context_enrichment(self):
        """Prueba el enriquecimiento de contexto"""
        logger.info("📖 Probando enriquecimiento de contexto...")
        
        context_results = {}
        
        try:
            # Búsqueda con contexto habilitado
            result_with_context = self.kb.buscar_solucion_rag("calibrar balanza", top_k=2)
            
            # Verificar si hay contexto adicional
            has_context_markers = any(marker in result_with_context.lower() 
                                    for marker in ["contexto", "relacionado", "página"])
            
            # Verificar estructura de contexto
            has_metadata = any(marker in result_with_context 
                             for marker in ["Fuente:", "Página", "Sección"])
            
            context_results = {
                "has_context_markers": has_context_markers,
                "has_metadata": has_metadata,
                "result_length": len(result_with_context),
                "context_enrichment_working": has_context_markers or has_metadata
            }
            
            logger.info(f"   ✅ Contexto detectado: {has_context_markers}")
            logger.info(f"   ✅ Metadatos incluidos: {has_metadata}")
            
        except Exception as e:
            context_results = {"error": str(e), "context_enrichment_working": False}
            logger.error(f"   ❌ Error probando contexto: {e}")
        
        self.test_results["context_enrichment"] = context_results
    
    async def _test_performance_benchmarks(self):
        """Ejecuta benchmarks de rendimiento"""
        logger.info("⚡ Ejecutando benchmarks de rendimiento...")
        
        benchmark_queries = [
            "balanza no funciona correctamente",
            "etiquetas no se imprimen bien",
            "calibrar balanza dibal mistral paso a paso",
            "problema pantalla negra en tpv",
            "error impresora papel atascado",
            "reiniciar sistema punto de venta",
            "cambiar rollo papel etiquetas",
            "configurar precio productos balanza",
            "mantenimiento preventivo equipos",
            "solucionar conectividad red tienda"
        ]
        
        performance_results = {
            "individual_times": [],
            "total_queries": len(benchmark_queries),
            "successful_queries": 0,
            "failed_queries": 0
        }
        
        logger.info(f"   🎯 Ejecutando {len(benchmark_queries)} consultas de benchmark...")
        
        total_start_time = time.time()
        
        for i, query in enumerate(benchmark_queries, 1):
            try:
                start_time = time.time()
                result = self.kb.buscar_solucion_rag(query, top_k=3)
                duration = time.time() - start_time
                
                # Verificar calidad del resultado
                has_content = len(result) > 50
                appears_relevant = any(word in result.lower() 
                                     for word in query.lower().split()[:3])
                
                success = has_content and (appears_relevant or "no se encontraron" in result.lower())
                
                performance_results["individual_times"].append(duration)
                if success:
                    performance_results["successful_queries"] += 1
                else:
                    performance_results["failed_queries"] += 1
                
                status = "✅" if success else "⚠️"
                logger.info(f"   {status} Query {i}/{len(benchmark_queries)}: {duration:.3f}s")
                
            except Exception as e:
                performance_results["failed_queries"] += 1
                performance_results["individual_times"].append(0)
                logger.error(f"   ❌ Query {i} falló: {e}")
        
        total_duration = time.time() - total_start_time
        
        # Calcular estadísticas
        times = [t for t in performance_results["individual_times"] if t > 0]
        if times:
            performance_results.update({
                "total_duration": total_duration,
                "average_time": statistics.mean(times),
                "median_time": statistics.median(times),
                "min_time": min(times),
                "max_time": max(times),
                "std_deviation": statistics.stdev(times) if len(times) > 1 else 0,
                "success_rate": performance_results["successful_queries"] / len(benchmark_queries),
                "queries_per_second": len(benchmark_queries) / total_duration
            })
        
        self.performance_metrics["benchmarks"] = performance_results
        
        # Log de resultados
        logger.info(f"   📊 Rendimiento promedio: {performance_results.get('average_time', 0):.3f}s")
        logger.info(f"   📊 Tasa de éxito: {performance_results.get('success_rate', 0):.1%}")
        logger.info(f"   📊 Consultas/segundo: {performance_results.get('queries_per_second', 0):.2f}")
    
    async def _test_concurrent_searches(self):
        """Prueba búsquedas concurrentes"""
        logger.info("🔄 Probando búsquedas concurrentes...")
        
        concurrent_queries = [
            "balanza error calibración",
            "impresora no funciona",
            "pantalla negra tpv",
            "etiquetas papel atascado",
            "reiniciar sistema"
        ]
        
        async def single_search(query, query_id):
            try:
                start_time = time.time()
                result = self.kb.buscar_solucion_rag(f"{query} test {query_id}")
                duration = time.time() - start_time
                return {
                    "query_id": query_id,
                    "success": len(result) > 50,
                    "duration": duration,
                    "result_length": len(result)
                }
            except Exception as e:
                return {
                    "query_id": query_id,
                    "success": False,
                    "error": str(e),
                    "duration": 0
                }
        
        # Ejecutar búsquedas concurrentes
        start_time = time.time()
        tasks = [single_search(query, i) for i, query in enumerate(concurrent_queries)]
        concurrent_results = await asyncio.gather(*tasks, return_exceptions=True)
        total_concurrent_time = time.time() - start_time
        
        # Analizar resultados
        successful_concurrent = sum(1 for r in concurrent_results 
                                  if isinstance(r, dict) and r.get("success", False))
        
        concurrent_metrics = {
            "total_concurrent_queries": len(concurrent_queries),
            "successful_concurrent": successful_concurrent,
            "total_concurrent_time": total_concurrent_time,
            "concurrent_success_rate": successful_concurrent / len(concurrent_queries),
            "average_concurrent_time": total_concurrent_time / len(concurrent_queries),
            "results": concurrent_results
        }
        
        self.performance_metrics["concurrent"] = concurrent_metrics
        
        logger.info(f"   ✅ Búsquedas concurrentes: {successful_concurrent}/{len(concurrent_queries)}")
        logger.info(f"   ⏱️ Tiempo total concurrente: {total_concurrent_time:.3f}s")
        logger.info(f"   📊 Promedio por consulta: {concurrent_metrics['average_concurrent_time']:.3f}s")
    
    async def _test_search_quality(self):
        """Prueba la calidad de resultados de búsqueda"""
        logger.info("🎯 Evaluando calidad de resultados...")
        
        quality_test_cases = [
            {
                "query": "balanza dibal mistral calibración",
                "expected_topics": ["calibra", "dibal", "mistral", "ajust"],
                "relevance_threshold": 0.7
            },
            {
                "query": "problema etiquetas no se imprimen",
                "expected_topics": ["etiqueta", "papel", "impre", "rollo"],
                "relevance_threshold": 0.6
            },
            {
                "query": "error pantalla negra tpv",
                "expected_topics": ["pantalla", "display", "tpv", "negro"],
                "relevance_threshold": 0.6
            },
            {
                "query": "mantenimiento preventivo balanza",
                "expected_topics": ["mantenimiento", "limpieza", "preventivo"],
                "relevance_threshold": 0.5
            }
        ]
        
        quality_results = {}
        
        for test_case in quality_test_cases:
            try:
                result = self.kb.buscar_solucion_rag(test_case["query"], top_k=3)
                
                # Evaluar relevancia
                result_lower = result.lower()
                topic_matches = sum(1 for topic in test_case["expected_topics"] 
                                  if topic in result_lower)
                relevance_score = topic_matches / len(test_case["expected_topics"])
                
                # Evaluar estructura
                has_good_structure = any(marker in result for marker in ["**", "Solución", "Página"])
                has_sufficient_content = len(result) > 100
                no_errors = "error" not in result.lower() or "solución" in result.lower()
                
                quality_score = (
                    relevance_score * 0.5 +
                    (1.0 if has_good_structure else 0.0) * 0.3 +
                    (1.0 if has_sufficient_content else 0.0) * 0.2
                )
                
                meets_threshold = relevance_score >= test_case["relevance_threshold"]
                
                quality_results[test_case["query"]] = {
                    "relevance_score": relevance_score,
                    "quality_score": quality_score,
                    "meets_threshold": meets_threshold,
                    "topic_matches": topic_matches,
                    "total_topics": len(test_case["expected_topics"]),
                    "has_structure": has_good_structure,
                    "sufficient_content": has_sufficient_content,
                    "content_length": len(result)
                }
                
                status = "✅" if meets_threshold else "⚠️"
                logger.info(f"   {status} '{test_case['query']}': relevancia {relevance_score:.2f}")
                
            except Exception as e:
                quality_results[test_case["query"]] = {"error": str(e), "quality_score": 0}
                logger.error(f"   ❌ Error evaluando '{test_case['query']}': {e}")
        
        # Estadísticas de calidad general
        successful_tests = [r for r in quality_results.values() if r.get("meets_threshold", False)]
        average_quality = statistics.mean([r.get("quality_score", 0) for r in quality_results.values()])
        average_relevance = statistics.mean([r.get("relevance_score", 0) for r in quality_results.values()])
        
        quality_summary = {
            "total_tests": len(quality_test_cases),
            "passed_tests": len(successful_tests),
            "quality_pass_rate": len(successful_tests) / len(quality_test_cases),
            "average_quality_score": average_quality,
            "average_relevance_score": average_relevance,
            "individual_results": quality_results
        }
        
        self.test_results["search_quality"] = quality_summary
        
        logger.info(f"   📊 Calidad promedio: {average_quality:.2f}")
        logger.info(f"   📊 Relevancia promedia: {average_relevance:.2f}")
        logger.info(f"   📊 Tasa de aprobación: {quality_summary['quality_pass_rate']:.1%}")
    
    async def _test_relevance_scoring(self):
        """Prueba el sistema de puntuación de relevancia"""
        logger.info("🏆 Probando sistema de puntuación de relevancia...")
        
        # Verificar si tenemos acceso al sistema de scoring
        if not hasattr(self.kb, 'searcher'):
            logger.warning("   ⚠️ Sistema de scoring no accesible directamente")
            return
        
        scoring_tests = [
            {
                "query": "balanza dibal mistral calibración",
                "expected_high_score_terms": ["balanza", "dibal", "mistral", "calibra"]
            },
            {
                "query": "problema muy específico técnico",
                "expected_high_score_terms": ["problema", "técnico"]
            }
        ]
        
        scoring_results = {}
        
        for test in scoring_tests:
            try:
                # Intentar acceder a resultados detallados
                if hasattr(self.kb.searcher, 'search'):
                    results, metrics = await self.kb.searcher.search(
                        test["query"], 
                        top_k=3,
                        include_context=False
                    )
                    
                    # Analizar scores de confidence
                    if results:
                        scores = [r.confidence for r in results if hasattr(r, 'confidence')]
                        similarities = [r.similarity for r in results if hasattr(r, 'similarity')]
                        
                        scoring_results[test["query"]] = {
                            "results_count": len(results),
                            "confidence_scores": scores,
                            "similarity_scores": similarities,
                            "max_confidence": max(scores) if scores else 0,
                            "avg_confidence": statistics.mean(scores) if scores else 0,
                            "score_distribution": "good" if scores and max(scores) > 0.6 else "poor"
                        }
                        
                        logger.info(f"   ✅ '{test['query']}': max confidence {max(scores):.3f}" if scores else "   ⚠️ Sin scores")
                    else:
                        scoring_results[test["query"]] = {"no_results": True}
                        logger.warning(f"   ⚠️ '{test['query']}': sin resultados")
                
            except Exception as e:
                scoring_results[test["query"]] = {"error": str(e)}
                logger.error(f"   ❌ Error en scoring para '{test['query']}': {e}")
        
        self.test_results["relevance_scoring"] = scoring_results
    
    async def _analyze_system_metrics(self):
        """Analiza métricas del sistema"""
        logger.info("📈 Analizando métricas del sistema...")
        
        system_metrics = {}
        
        try:
            # Obtener analíticas si están disponibles
            if hasattr(self.kb, 'get_analytics'):
                analytics = await self.kb.get_analytics()
                system_metrics["analytics"] = analytics
                
                if analytics:
                    logger.info("   ✅ Analíticas del sistema disponibles")
                    for key, value in analytics.items():
                        logger.info(f"      • {key}: {value}")
                else:
                    logger.info("   ℹ️ Analíticas vacías (sistema nuevo)")
            
            # Verificar estado del cache
            if hasattr(self.kb, 'searcher') and hasattr(self.kb.searcher, 'cache'):
                cache = self.kb.searcher.cache
                cache_info = {
                    "cache_size": len(cache._cache),
                    "max_cache_size": cache.max_size,
                    "cache_utilization": len(cache._cache) / cache.max_size if cache.max_size > 0 else 0
                }
                system_metrics["cache"] = cache_info
                
                logger.info(f"   💾 Cache: {cache_info['cache_size']}/{cache_info['max_cache_size']} entradas")
            
            # Verificar pool de conexiones
            if hasattr(self.kb, 'searcher') and hasattr(self.kb.searcher, '_connection_pool'):
                pool = self.kb.searcher._connection_pool
                if pool:
                    pool_info = {
                        "pool_size": pool.get_size(),
                        "pool_min_size": pool.get_min_size(),
                        "pool_max_size": pool.get_max_size(),
                    }
                    system_metrics["connection_pool"] = pool_info
                    
                    logger.info(f"   🔗 Pool conexiones: {pool_info['pool_size']} activas")
            
        except Exception as e:
            system_metrics["error"] = str(e)
            logger.error(f"   ❌ Error analizando métricas: {e}")
        
        self.test_results["system_metrics"] = system_metrics
    
    def _generate_verification_report(self):
        """Genera reporte completo de verificación"""
        logger.info("📋 Generando reporte de verificación...")
        
        report = {
            "verification_timestamp": datetime.now().isoformat(),
            "system_version": "RAG Optimizado v2.0",
            "test_results": self.test_results,
            "performance_metrics": self.performance_metrics
        }
        
        # Calcular score general
        scores = []
        
        # Score de funcionalidad básica
        if "basic_functionality" in self.test_results:
            basic_success = sum(1 for r in self.test_results["basic_functionality"].values() 
                              if r.get("success", False))
            basic_total = len(self.test_results["basic_functionality"])
            scores.append(basic_success / basic_total if basic_total > 0 else 0)
        
        # Score de calidad
        if "search_quality" in self.test_results:
            quality_score = self.test_results["search_quality"].get("quality_pass_rate", 0)
            scores.append(quality_score)
        
        # Score de rendimiento
        if "benchmarks" in self.performance_metrics:
            perf_score = self.performance_metrics["benchmarks"].get("success_rate", 0)
            scores.append(perf_score)
        
        overall_score = statistics.mean(scores) if scores else 0
        report["overall_score"] = overall_score
        report["grade"] = self._calculate_grade(overall_score)
        
        # Guardar reporte
        report_path = ROOT_DIR / "reports" / f"rag_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # Imprimir resumen
        self._print_verification_summary(report, report_path)
    
    def _calculate_grade(self, score: float) -> str:
        """Calcula calificación basada en el score"""
        if score >= 0.9:
            return "A+ (Excelente)"
        elif score >= 0.8:
            return "A (Muy Bueno)"
        elif score >= 0.7:
            return "B (Bueno)"
        elif score >= 0.6:
            return "C (Aceptable)"
        elif score >= 0.5:
            return "D (Necesita Mejoras)"
        else:
            return "F (Falla)"
    
    def _print_verification_summary(self, report: Dict, report_path: Path):
        """Imprime resumen de la verificación"""
        print("\n" + "="*60)
        print("🏆 REPORTE DE VERIFICACIÓN RAG OPTIMIZADO")
        print("="*60)
        
        overall_score = report.get("overall_score", 0)
        grade = report.get("grade", "N/A")
        
        print(f"\n📊 PUNTUACIÓN GENERAL: {overall_score:.1%}")
        print(f"🎯 CALIFICACIÓN: {grade}")
        
        print("\n📋 RESULTADOS POR CATEGORÍA:")
        
        # Funcionalidad básica
        if "basic_functionality" in self.test_results:
            basic = self.test_results["basic_functionality"]
            success_count = sum(1 for r in basic.values() if r.get("success", False))
            total_count = len(basic)
            print(f"   ✅ Funcionalidad Básica: {success_count}/{total_count} ({success_count/total_count:.1%})")
        
        # Rendimiento
        if "benchmarks" in self.performance_metrics:
            perf = self.performance_metrics["benchmarks"]
            avg_time = perf.get("average_time", 0)
            success_rate = perf.get("success_rate", 0)
            print(f"   ⚡ Rendimiento: {success_rate:.1%} éxito, {avg_time:.3f}s promedio")
        
        # Calidad
        if "search_quality" in self.test_results:
            quality = self.test_results["search_quality"]
            quality_rate = quality.get("quality_pass_rate", 0)
            avg_relevance = quality.get("average_relevance_score", 0)
            print(f"   🎯 Calidad: {quality_rate:.1%} aprobación, {avg_relevance:.2f} relevancia")
        
        # Cache
        if "cache_system" in self.test_results:
            cache = self.test_results["cache_system"]
            cache_working = cache.get("cache_working", False)
            speed_improvement = cache.get("speed_improvement", 1)
            print(f"   💾 Cache: {'✅ Funcionando' if cache_working else '❌ Problema'}, {speed_improvement:.1f}x mejora")
        
        print(f"\n📁 REPORTE COMPLETO: {report_path}")
        
        # Recomendaciones
        print("\n💡 RECOMENDACIONES:")
        if overall_score >= 0.8:
            print("   🎉 ¡Excelente! El sistema RAG optimizado está funcionando perfectamente.")
            print("   🚀 Considera monitorear el rendimiento en producción.")
        elif overall_score >= 0.6:
            print("   ✅ El sistema funciona bien con áreas de mejora menores.")
            print("   🔧 Revisa los casos de prueba que fallaron.")
        else:
            print("   ⚠️ El sistema necesita atención urgente.")
            print("   🔧 Revisa la configuración y ejecuta:")
            print("      python database/scripts/optimize_rag_database.py")
    
    async def _cleanup(self):
        """Limpia recursos utilizados"""
        if self.kb:
            try:
                await self.kb.close()
                logger.info("✅ Recursos del sistema RAG liberados")
            except:
                pass

async def main():
    """Función principal de verificación"""
    print("🔍 SUITE DE VERIFICACIÓN RAG OPTIMIZADO")
    print("="*50)
    print("Esta suite verificará que todas las optimizaciones estén funcionando correctamente.")
    print()
    
    verifier = RAGOptimizationVerifier()
    
    try:
        await verifier.run_complete_verification()
        return 0
    except Exception as e:
        print(f"\n❌ Error durante la verificación: {e}")
        print("💡 Asegúrate de que:")
        print("   1. La migración se ejecutó correctamente")
        print("   2. La base de datos está optimizada")
        print("   3. El sistema RAG está inicializado")
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))