# =====================================================
# nodes/department_detection_system.py - Sistema de Detección de Departamentos
# =====================================================
"""
Sistema avanzado de detección de departamentos usando doble LLM para Eroski.

ARQUITECTURA:
1. LLM Básico: Extrae estructura clara del input
2. LLM Especializado: Interpreta semánticamente departamentos 
3. Búsqueda en BD: Encuentra coincidencias exactas o similares
4. Confirmación: Valida con el usuario

CASOS DE USO:
- "cosmético" → "Perfumería"
- "Pastelería" → "Panadería" 
- "productos de belleza" → "Perfumería"
- "carne" → "Carnicería"
- "electrónicos" → "Electrónica"
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from langchain_core.prompts import ChatPromptTemplate
import json
import asyncio
import re

class DepartmentDetectionSystem:
    """Sistema de detección de departamentos con doble LLM"""
    
    def __init__(self, llm, db_service, logger):
        self.llm = llm
        self.db_service = db_service
        self.logger = logger
        self._departamentos_cache = None
        
        # Configuración de confianza
        self.confidence_threshold_auto = 0.9  # Auto-aceptar si > 90%
        self.confidence_threshold_suggest = 0.3  # Sugerir si > 30%
        
    async def inicializar_cache_departamentos(self):
        """Cargar cache de departamentos desde BD"""
        try:
            # Usar el método existente del db_service
            if hasattr(self.db_service, 'get_all_departments'):
                self._departamentos_cache = await self.db_service.get_all_departments()
            else:
                # Fallback: cargar manualmente
                self._departamentos_cache = await self._cargar_departamentos_manual()
                
            self.logger.info(f"✅ Cache departamentos cargado: {len(self._departamentos_cache)} departamentos")
            
        except Exception as e:
            self.logger.error(f"❌ Error cargando departamentos: {e}")
            # Cache de emergencia con departamentos básicos
            self._departamentos_cache = self._get_departamentos_emergencia()
    
    async def _cargar_departamentos_manual(self) -> List[Dict]:
        """Cargar departamentos manual desde BD"""
        import asyncpg
        from config.settings import get_settings
        
        settings = get_settings()
        
        try:
            conn = await asyncpg.connect(
                host=settings.database_host,
                port=settings.database_port,
                user=settings.database_user,
                password=settings.database_password,
                database=settings.database_name
            )
            
            # Intentar cargar desde tabla departamentos
            rows = await conn.fetch("SELECT id, nombre FROM departamentos ORDER BY nombre")
            departments = [{"id": row["id"], "nombre": row["nombre"]} for row in rows]
            
            await conn.close()
            return departments
            
        except Exception as e:
            self.logger.warning(f"⚠️ No se pudo cargar desde BD: {e}")
            return self._get_departamentos_emergencia()
    
    def _get_departamentos_emergencia(self) -> List[Dict]:
        """Departamentos de emergencia si falla la BD"""
        return [
            {"id": 1, "nombre": "Carnicería"},
            {"id": 2, "nombre": "Panadería"}, 
            {"id": 3, "nombre": "Pescadería"},
            {"id": 4, "nombre": "Frutería"},
            {"id": 5, "nombre": "Charcutería"},
            {"id": 6, "nombre": "Perfumería"},
            {"id": 7, "nombre": "Farmacia"},
            {"id": 8, "nombre": "Textil"},
            {"id": 9, "nombre": "Hogar"},
            {"id": 10, "nombre": "Caja"},
            {"id": 11, "nombre": "Lácteos"},
            {"id": 12, "nombre": "Bebidas"},
            {"id": 13, "nombre": "Congelados"},
            {"id": 14, "nombre": "Electrónica"}
        ]

    async def detectar_departamento(self, user_input: str, state: Dict = None) -> Dict[str, Any]:
        """
        Método principal de detección usando flujo de doble LLM
        
        Returns:
        {
            "encontrado": bool,
            "departamento": str | None,
            "departamento_id": int | None,
            "requiere_confirmacion": bool,
            "sugerencia": str | None,
            "confianza": float,
            "input_original": str,
            "metodo_deteccion": str
        }
        """
        self.logger.info(f"🔍 Iniciando detección de departamento para: '{user_input}'")
        
        # PASO 1: LLM Básico - Extracción estructural
        datos_basicos = await self._extraer_datos_basico(user_input)
        
        # PASO 2: Verificar si hay departamento en datos básicos
        if datos_basicos.get("seccion"):
            self.logger.info(f"✅ LLM básico detectó departamento: {datos_basicos['seccion']}")
            return await self._procesar_departamento_detectado(
                datos_basicos["seccion"], 
                "llm_basico"
            )
        
        # PASO 3: LLM Especializado - Interpretación semántica
        self.logger.info("🧠 Activando LLM especializado para interpretación semántica")
        resultado_especializado = await self._interpretar_semanticamente(user_input)
        
        if resultado_especializado["es_departamento"]:
            return await self._procesar_departamento_detectado(
                resultado_especializado["departamento_normalizado"],
                "llm_especializado",
                resultado_especializado["confianza"]
            )
        
        # PASO 4: No se detectó departamento
        self.logger.info("❌ No se detectó departamento válido")
        return {
            "encontrado": False,
            "departamento": None,
            "departamento_id": None,
            "requiere_confirmacion": False,
            "sugerencia": None,
            "confianza": 0.0,
            "input_original": user_input,
            "metodo_deteccion": "ninguno"
        }

    async def _extraer_datos_basico(self, user_input: str) -> Dict[str, Any]:
        """LLM Básico: Extracción de datos estructurados claros"""
        
        departamentos_conocidos = []
        if self._departamentos_cache:
            departamentos_conocidos = [dept["nombre"] for dept in self._departamentos_cache[:15]]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""Eres un extractor de datos básicos para empleados de Eroski.

Extrae SOLO datos que sean claramente identificables:
- nombre: nombre completo
- numero_empleado: código alfanumérico (G101, A001, 1234)
- tienda: nombre de tienda
- seccion: SOLO si es claramente un departamento de supermercado

DEPARTAMENTOS CONOCIDOS EN EROSKI:
{', '.join(departamentos_conocidos)}

DEPARTAMENTOS OBVIOS: carnicería, panadería, pescadería, caja, frutería, charcutería, 
perfumería, farmacia, textil, hogar, lácteos, bebidas, congelados, pastelería

EJEMPLOS:
"Javier, G101, panadería" → {{"nombre": "Javier", "numero_empleado": "G101", "seccion": "panadería"}}
"cosmético" → {{}} (no es departamento claro)
"Soy de perfumería" → {{"seccion": "perfumería"}}
"Pastelería" → {{"seccion": "Pastelería"}}

RESPONDE JSON VÁLIDO - SOLO datos OBVIOS:"""),
            ("human", "Mensaje: {user_input}")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({"user_input": user_input})
        
        try:
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            
            datos = json.loads(content)
            self.logger.info(f"📊 LLM básico extrajo: {datos}")
            return datos
            
        except Exception as e:
            self.logger.warning(f"⚠️ Error parseando LLM básico: {e}")
            return {}

    async def _interpretar_semanticamente(self, user_input: str) -> Dict[str, Any]:
        """LLM Especializado: Interpretación semántica de departamentos"""
        
        # Obtener lista de departamentos conocidos
        departamentos_conocidos = []
        if self._departamentos_cache:
            departamentos_conocidos = [dept["nombre"] for dept in self._departamentos_cache]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""Eres un especialista en departamentos de supermercado Eroski.

Tu misión: determinar si el input del usuario se refiere a un departamento y normalizarlo.

DEPARTAMENTOS DISPONIBLES EN EROSKI:
{', '.join(departamentos_conocidos[:20])}

REGLAS DE INTERPRETACIÓN:
1. Analiza el PROPÓSITO/FUNCIÓN del término
2. Considera SINÓNIMOS y VARIACIONES
3. Contextualiza en un SUPERMERCADO
4. Rechaza términos que NO son departamentos

MAPPINGS INTELIGENTES:
- "cosmético", "belleza", "maquillaje" → "Perfumería" 
- "electrónicos", "tecnología", "móviles" → "Electrónica"
- "productos veganos", "alimentación" → "Alimentación"
- "carne", "carnes" → "Carnicería"
- "pan", "bollería" → "Panadería"
- "pastelería", "repostería", "dulces" → "Panadería"
- "pescado", "mariscos" → "Pescadería"
- "fruta", "frutas" → "Frutería"
- "ropa", "vestir" → "Textil"
- "medicinas", "medicamentos" → "Farmacia"
- "leche", "yogures" → "Lácteos"
- "hola", "gracias" → NO (no es departamento)

RESPONDE EN JSON:
{{
    "es_departamento": true/false,
    "departamento_normalizado": "nombre_departamento" o null,
    "razonamiento": "explicación breve",
    "confianza": 0.0-1.0
}}

IMPORTANTE: Solo responde 'true' si realmente es un departamento de supermercado."""),
            ("human", "Input del usuario: '{user_input}'\n\n¿Es esto un departamento? ¿Cómo se llamaría en Eroski?")
        ])
        
        chain = prompt | self.llm
        response = await chain.ainvoke({"user_input": user_input})
        
        try:
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            
            resultado = json.loads(content)
            self.logger.info(f"🧠 LLM especializado: {resultado}")
            return resultado
            
        except Exception as e:
            self.logger.error(f"❌ Error en LLM especializado: {e}")
            return {
                "es_departamento": False,
                "departamento_normalizado": None,
                "razonamiento": "Error de procesamiento",
                "confianza": 0.0
            }

    async def _procesar_departamento_detectado(self, departamento: str, metodo: str, confianza_llm: float = 0.8) -> Dict[str, Any]:
        """Procesar departamento detectado y buscar en BD"""
        
        # Buscar coincidencia exacta o similar en BD
        departamento_bd, confianza_bd = self._buscar_departamento_en_bd(departamento)
        
        # Combinar confianzas
        confianza_final = min(confianza_llm, confianza_bd) if departamento_bd else 0.0
        
        if departamento_bd:
            # Encontrado en BD
            return {
                "encontrado": True,
                "departamento": departamento_bd["nombre"],
                "departamento_id": departamento_bd.get("id"),
                "requiere_confirmacion": confianza_final < self.confidence_threshold_auto,
                "sugerencia": departamento_bd["nombre"],
                "confianza": confianza_final,
                "input_original": departamento,
                "metodo_deteccion": metodo
            }
        else:
            # No se encontró en BD, buscar similares
            sugerencias = self._obtener_sugerencias_similares(departamento)
            
            return {
                "encontrado": False,
                "departamento": None,
                "departamento_id": None,
                "requiere_confirmacion": len(sugerencias) > 0,
                "sugerencia": sugerencias[0] if sugerencias else None,
                "sugerencias_multiples": sugerencias,
                "confianza": 0.0,
                "input_original": departamento,
                "metodo_deteccion": metodo
            }

    def _buscar_departamento_en_bd(self, departamento: str) -> Tuple[Optional[Dict], float]:
        """Buscar departamento en la base de datos con scoring de confianza"""
        if not self._departamentos_cache:
            return None, 0.0
        
        departamento_lower = departamento.lower().strip()
        
        # 1. Coincidencia exacta
        for dept in self._departamentos_cache:
            if dept["nombre"].lower() == departamento_lower:
                return dept, 1.0
        
        # 2. Coincidencia parcial fuerte (contiene)
        for dept in self._departamentos_cache:
            nombre_dept = dept["nombre"].lower()
            if (departamento_lower in nombre_dept or 
                nombre_dept in departamento_lower) and len(departamento_lower) > 3:
                return dept, 0.85
        
        # 3. Mappings específicos
        mappings = {
            "pasteleria": "Panadería",
            "pastelería": "Panadería",
            "reposteria": "Panadería", 
            "repostería": "Panadería",
            "cosmetico": "Perfumería",
            "cosmético": "Perfumería",
            "belleza": "Perfumería",
            "maquillaje": "Perfumería",
            "carne": "Carnicería",
            "carnes": "Carnicería",
            "pescado": "Pescadería",
            "mariscos": "Pescadería",
            "fruta": "Frutería",
            "frutas": "Frutería",
            "pan": "Panadería",
            "bolleria": "Panadería",
            "ropa": "Textil",
            "vestir": "Textil",
            "medicinas": "Farmacia",
            "medicamentos": "Farmacia",
            "leche": "Lácteos",
            "yogures": "Lácteos",
            "electronicos": "Electrónica",
            "tecnologia": "Electrónica"
        }
        
        mapped_dept = mappings.get(departamento_lower)
        if mapped_dept:
            for dept in self._departamentos_cache:
                if dept["nombre"].lower() == mapped_dept.lower():
                    return dept, 0.9
        
        # 4. Similitud por caracteres
        best_match = None
        best_score = 0.0
        
        for dept in self._departamentos_cache:
            score = self._calcular_similitud(departamento_lower, dept["nombre"].lower())
            if score > best_score and score > 0.6:
                best_match = dept
                best_score = score
        
        return best_match, best_score if best_match else 0.0

    def _calcular_similitud(self, str1: str, str2: str) -> float:
        """Calcular similitud entre dos strings"""
        # Similitud básica por caracteres comunes
        set1 = set(str1.lower())
        set2 = set(str2.lower())
        
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0

    def _obtener_sugerencias_similares(self, departamento: str, max_sugerencias: int = 3) -> List[str]:
        """Obtener sugerencias de departamentos similares"""
        if not self._departamentos_cache:
            return []
        
        # Ordenar por similitud
        departamentos_con_score = []
        for dept in self._departamentos_cache:
            score = self._calcular_similitud(departamento, dept["nombre"])
            if score > self.confidence_threshold_suggest:
                departamentos_con_score.append((dept["nombre"], score))
        
        # Ordenar por score descendente
        departamentos_con_score.sort(key=lambda x: x[1], reverse=True)
        
        return [dept[0] for dept in departamentos_con_score[:max_sugerencias]]

    async def generar_mensaje_confirmacion(self, resultado: Dict[str, Any]) -> str:
        """Generar mensaje de confirmación para el usuario"""
        if resultado["encontrado"] and resultado["requiere_confirmacion"]:
            return (
                f"🧭 **Departamento detectado:** {resultado['sugerencia']}\n\n"
                f"He encontrado este departamento que coincide con '{resultado['input_original']}':\n"
                f"🏢 **{resultado['sugerencia']}**\n\n"
                f"¿Es correcto este departamento? (Sí/No)"
            )
        elif not resultado["encontrado"] and resultado["sugerencia"]:
            sugerencias = resultado.get("sugerencias_multiples", [resultado["sugerencia"]])
            mensaje = (
                f"No encontré un departamento que coincida exactamente con '{resultado['input_original']}'.\n\n"
                f"¿Te refieres a alguno de estos departamentos?\n\n"
            )
            for i, sugerencia in enumerate(sugerencias, 1):
                mensaje += f"{i}. {sugerencia}\n"
            
            mensaje += "\n¿Podrías especificar el número o el nombre exacto del departamento?"
            return mensaje
        else:
            # Mostrar departamentos disponibles 
            departamentos_disponibles = []
            if self._departamentos_cache:
                departamentos_disponibles = [dept["nombre"] for dept in self._departamentos_cache[:8]]
            
            mensaje = (
                f"No encontré un departamento que coincida con '{resultado.get('input_original', 'tu entrada')}'.\n\n"
                "Estos son algunos departamentos disponibles:\n"
            )
            
            for i, dept in enumerate(departamentos_disponibles, 1):
                mensaje += f"{i}. {dept}\n"
            
            mensaje += "\n¿Podrías especificar el nombre exacto del departamento?"
            return mensaje

    async def procesar_mensaje_usuario(self, user_input: str, state: Dict) -> Dict[str, Any]:
        """Método público para procesar mensaje del usuario con detección mejorada"""
        
        # 1. Extraer datos básicos primero
        datos_basicos = await self._extraer_datos_basico(user_input)
        
        # 2. Si no hay departamento en datos básicos, usar detector especializado  
        if not datos_basicos.get("seccion"):
            # Solo analizar como departamento si parece ser esa la intención
            words = user_input.strip().split()
            if (len(words) <= 3 and  # Mensajes cortos
                not any(datos_basicos.get(campo) for campo in ["nombre", "numero_empleado", "tienda"])):
                
                resultado_dept = await self.detectar_departamento(user_input, state)
                
                # Agregar información del departamento detectado
                if resultado_dept["encontrado"] or resultado_dept["sugerencia"]:
                    datos_basicos["_department_detection"] = resultado_dept
                    if resultado_dept["encontrado"]:
                        datos_basicos["seccion"] = resultado_dept["departamento"]
        
        return datos_basicos


# =====================================================
# FUNCIONES DE UTILIDAD
# =====================================================

async def test_department_detection():
    """Función de test rápido para desarrollo"""
    
    class MockLLM:
        async def ainvoke(self, input_dict):
            # Mock simple para testing
            user_input = input_dict.get("user_input", "")
            
            class MockResponse:
                content = '{"seccion": "' + user_input + '"}' if "ería" in user_input else '{}'
            
            return MockResponse()
    
    class MockDBService:
        async def get_all_departments(self):
            return [
                {"id": 1, "nombre": "Carnicería"},
                {"id": 2, "nombre": "Panadería"},
                {"id": 3, "nombre": "Pescadería"}
            ]
    
    import logging
    logger = logging.getLogger("test")
    
    # Test básico
    detector = DepartmentDetectionSystem(MockLLM(), MockDBService(), logger)
    await detector.inicializar_cache_departamentos()
    
    casos_test = ["Pastelería", "cosmético", "carne"]
    for caso in casos_test:
        resultado = await detector.detectar_departamento(caso)
        print(f"'{caso}' → {resultado}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_department_detection())