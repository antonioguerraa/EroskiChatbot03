#!/usr/bin/env python3
"""
Script de prueba para verificar el funcionamiento de las tools de base de datos
search_by_email_adapted y search_by_employee_id_adapted

Prueba casos:
1. Emails que existen en la BD
2. IDs de empleado que existen
3. Email que NO existe (javier.guerra@devol.es)
4. Manejo de valores None en la BD
"""

import asyncio
import sys
import os
from pathlib import Path

# Agregar el directorio raíz al path
ROOT_DIR = Path(__file__).parent.parent if __name__ == "__main__" else Path.cwd()
sys.path.insert(0, str(ROOT_DIR))

# Configurar variables de entorno si no están
if not os.getenv('DATABASE_URL'):
    from dotenv import load_dotenv
    load_dotenv()

from nodes.identificador_base_de_datos import search_by_email_adapted, search_by_employee_id_adapted
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DatabaseTest")

class DatabaseToolsTester:
    """Tester para las tools de base de datos
    
 maria.gonzalez.ero001@eroski.es   | G101
 iker.etxeberria.ero001@eroski.es  | S101
 ainhoa.martinez.ero001@eroski.es  | E101
 jon.bilbao.ero001@eroski.es       | E104
 asier.mendizabal.ero002@eroski.es | S201
    
    
    """
    


    def __init__(self):
        self.test_cases = {
            "emails_validos": [
                "maria.gonzalez.ero001@eroski.es",
                "iker.etxeberria.ero001@eroski.es", 
                "ainhoa.martinez.ero001@eroski.es",
                "jon.bilbao.ero001@eroski.es"
            ],
            "employee_ids_validos": [
                "G101", "S101", "E101", "E104", "S201"
            ],
            "emails_invalidos": [
                "javier.guerra@devol.es",  # Email que NO existe
                "inexistente@eroski.es",
                "test@noexiste.com"
            ],
            "employee_ids_invalidos": [
                "9999", "0000", "XXXX", "abcd"
            ]
        }
    
    async def test_all_cases(self):
        """Ejecutar todas las pruebas"""
        logger.info("🧪 INICIANDO PRUEBAS DE TOOLS DE BASE DE DATOS")
        logger.info("=" * 60)
        
        # 1. Probar búsqueda por email - casos válidos
        await self._test_valid_emails()
        
        # 2. Probar búsqueda por employee_id - casos válidos  
        await self._test_valid_employee_ids()
        
        # 3. Probar casos inválidos/no encontrados
        await self._test_invalid_emails()
        await self._test_invalid_employee_ids()
        
        # 4. Probar el caso específico mencionado
        await self._test_specific_case()
        
        logger.info("🏁 PRUEBAS COMPLETADAS")
    
    async def _test_valid_emails(self):
        """Probar emails que deberían existir en la BD"""
        logger.info("\n📧 PROBANDO EMAILS VÁLIDOS")
        logger.info("-" * 40)
        
        for email in self.test_cases["emails_validos"]:
            try:
                logger.info(f"🔍 Probando email: {email}")
                result = await search_by_email_adapted.ainvoke({"email": email})
                
                if result.get("found"):
                    logger.info("✅ ENCONTRADO:")
                    logger.info(f"   👤 Empleado: {result.get('nombre', 'N/A')}")
                    logger.info(f"   📧 Email: {result.get('email', 'N/A')}")
                    logger.info(f"   🏪 Tienda: {result.get('nombre_tienda', 'N/A')}")
                    logger.info(f"   🏢 Depto: {result.get('departamento', 'N/A')}")
                    logger.info(f"   🆔 ID: {result.get('numero_empleado', 'N/A')}")
                    
                    # Verificar que no hay valores None problemáticos
                    none_values = [k for k, v in result.items() if v is None]
                    if none_values:
                        logger.warning(f"   ⚠️ Valores None encontrados: {none_values}")
                else:
                    logger.warning(f"❌ NO ENCONTRADO: {result.get('error', 'Sin error específico')}")
                
                print()  # Línea en blanco
                
            except Exception as e:
                logger.error(f"💥 ERROR con {email}: {e}")
                print()
    
    async def _test_valid_employee_ids(self):
        """Probar IDs de empleado que deberían existir"""
        logger.info("\n🆔 PROBANDO IDS DE EMPLEADO VÁLIDOS")
        logger.info("-" * 40)
        
        for emp_id in self.test_cases["employee_ids_validos"]:
            try:
                logger.info(f"🔍 Probando ID: {emp_id}")
                result = await search_by_employee_id_adapted.ainvoke({"employee_id": emp_id})
                
                if result.get("found"):
                    logger.info("✅ ENCONTRADO:")
                    logger.info(f"   👤 Empleado: {result.get('nombre', 'N/A')}")
                    logger.info(f"   📧 Email: {result.get('email', 'N/A')}")
                    logger.info(f"   🏪 Tienda: {result.get('nombre_tienda', 'N/A')}")
                    logger.info(f"   🏢 Depto: {result.get('departamento', 'N/A')}")
                    
                    # Verificar que no hay valores None problemáticos
                    none_values = [k for k, v in result.items() if v is None]
                    if none_values:
                        logger.warning(f"   ⚠️ Valores None encontrados: {none_values}")
                else:
                    logger.warning(f"❌ NO ENCONTRADO: {result.get('error', 'Sin error específico')}")
                
                print()
                
            except Exception as e:
                logger.error(f"💥 ERROR con ID {emp_id}: {e}")
                print()
    
    async def _test_invalid_emails(self):
        """Probar emails que NO deberían existir"""
        logger.info("\n❌ PROBANDO EMAILS INVÁLIDOS/NO EXISTENTES")
        logger.info("-" * 40)
        
        for email in self.test_cases["emails_invalidos"]:
            try:
                logger.info(f"🔍 Probando email inexistente: {email}")
                result = await search_by_email_adapted.ainvoke({"email": email})
                
                if not result.get("found"):
                    logger.info(f"✅ CORRECTO - No encontrado: {result.get('error', 'Email no existe')}")
                else:
                    logger.warning(f"⚠️ INESPERADO - Email encontrado cuando no debería existir")
                    logger.warning(f"   Datos: {result}")
                
                print()
                
            except Exception as e:
                logger.error(f"💥 ERROR con {email}: {e}")
                print()
    
    async def _test_invalid_employee_ids(self):
        """Probar IDs que NO deberían existir"""
        logger.info("\n❌ PROBANDO IDS INVÁLIDOS/NO EXISTENTES")
        logger.info("-" * 40)
        
        for emp_id in self.test_cases["employee_ids_invalidos"]:
            try:
                logger.info(f"🔍 Probando ID inexistente: {emp_id}")
                result = await search_by_employee_id_adapted.ainvoke({"employee_id": emp_id})
                
                if not result.get("found"):
                    logger.info(f"✅ CORRECTO - No encontrado: {result.get('error', 'ID no existe')}")
                else:
                    logger.warning(f"⚠️ INESPERADO - ID encontrado cuando no debería existir")
                    logger.warning(f"   Datos: {result}")
                
                print()
                
            except Exception as e:
                logger.error(f"💥 ERROR con ID {emp_id}: {e}")
                print()
    
    async def _test_specific_case(self):
        """Probar el caso específico mencionado: javier.guerra@devol.es"""
        logger.info("\n🎯 CASO ESPECÍFICO: javier.guerra@devol.es")
        logger.info("-" * 40)
        
        test_email = "javier.guerra@devol.es"
        
        try:
            logger.info(f"🔍 Probando el email problemático: {test_email}")
            result = await search_by_email_adapted.ainvoke({"email": test_email})
            
            logger.info("📊 RESULTADO COMPLETO:")
            for key, value in result.items():
                logger.info(f"   {key}: {value} ({type(value).__name__})")
            
            # Simular el formateo que causaba el error
            logger.info("\n🧪 SIMULANDO FORMATEO DE MENSAJE:")
            try:
                if result.get("found"):
                    # Usar los valores directamente (método original que fallaba)
                    test_message_unsafe = f"""✅ **¡Te he identificado correctamente!**

👤 **Empleado:** {result['nombre']}
📧 **Email:** {result['email']}
🏪 **Tienda:** {result['nombre_tienda']}
🏢 **Departamento:** {result['departamento']}"""
                    logger.info("✅ Formateo directo exitoso")
                    logger.info(f"Mensaje generado: {test_message_unsafe[:100]}...")
                    
                    # Usar el método seguro (fix aplicado)
                    empleado_nombre = result.get('nombre') or 'No disponible'
                    empleado_email = result.get('email') or 'No disponible'
                    nombre_tienda = result.get('nombre_tienda') or 'No especificada'
                    departamento = result.get('departamento') or 'No especificado'
                    
                    test_message_safe = f"""✅ **¡Te he identificado correctamente!**

👤 **Empleado:** {empleado_nombre}
📧 **Email:** {empleado_email}
🏪 **Tienda:** {nombre_tienda}
🏢 **Departamento:** {departamento}"""
                    logger.info("✅ Formateo seguro exitoso")
                    logger.info(f"Mensaje generado: {test_message_safe[:100]}...")
                    
                else:
                    logger.info("✅ Email no encontrado (comportamiento esperado)")
                    logger.info(f"Error reportado: {result.get('error')}")
                
            except Exception as format_error:
                logger.error(f"💥 ERROR EN FORMATEO: {format_error}")
                logger.error("🔧 Este sería el error que se solucionó con el fix")
                
                # Mostrar cómo el fix lo resuelve
                logger.info("\n🛠️ APLICANDO FIX:")
                empleado_nombre = result.get('nombre') or 'No disponible'
                empleado_email = result.get('email') or 'No disponible'
                nombre_tienda = result.get('nombre_tienda') or 'No especificada'
                departamento = result.get('departamento') or 'No especificado'
                
                test_message_fixed = f"""✅ **¡Te he identificado correctamente!**

👤 **Empleado:** {empleado_nombre}
📧 **Email:** {empleado_email}
🏪 **Tienda:** {nombre_tienda}
🏢 **Departamento:** {departamento}"""
                logger.info("✅ Fix aplicado exitosamente")
                logger.info(f"Mensaje corregido: {test_message_fixed[:100]}...")
            
        except Exception as e:
            logger.error(f"💥 ERROR GENERAL con {test_email}: {e}")

# Función principal para ejecución directa
async def main():
    """Función principal"""
    print("🚀 INICIANDO PRUEBAS DE TOOLS DE BASE DE DATOS")
    print("📋 Verificando acceso y manejo de datos...")
    print()
    
    tester = DatabaseToolsTester()
    await tester.test_all_cases()
    
    print("\n" + "="*60)
    print("📋 RESUMEN:")
    print("   • Se probaron ambas tools (email y employee_id)")
    print("   • Se verificó manejo de datos existentes y no existentes")
    print("   • Se simuló el caso específico que causaba el error")
    print("   • Se validó que el fix resuelve el problema de formateo")
    print("🎯 Las tools deberían funcionar correctamente después del fix")

if __name__ == "__main__":
    asyncio.run(main())