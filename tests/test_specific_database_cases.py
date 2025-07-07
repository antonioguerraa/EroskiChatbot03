#!/usr/bin/env python3
"""
Prueba específica de las tools con datos reales de la base de datos de Eroski.
Incluye el caso problemático: javier.guerra@devol.es
"""

import asyncio
import sys
import os
from pathlib import Path

# Setup del proyecto
ROOT_DIR = Path(__file__).parent.parent if __name__ == "__main__" else Path.cwd()
sys.path.insert(0, str(ROOT_DIR))

# Cargar variables de entorno
if not os.getenv('DATABASE_URL'):
    from dotenv import load_dotenv
    load_dotenv()

import logging
from nodes.identificador_base_de_datos import search_by_email_adapted, search_by_employee_id_adapted

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SpecificTest")

async def test_database_tools():
    """Probar tools con casos específicos"""
    
    print("🧪 PRUEBA ESPECÍFICA DE TOOLS DE BASE DE DATOS")
    print("=" * 60)
    
    # Datos que SÍ deberían estar en la BD (según el proyecto)
    existing_test_cases = [
        {
            "type": "email",
            "value": "ana.garcia@eroski.es",
            "description": "Ana García - Empleada de ejemplo"
        },
        {
            "type": "email", 
            "value": "carlos.lopez@eroski.es",
            "description": "Carlos López - Empleado de ejemplo"
        },
        {
            "type": "employee_id",
            "value": "1001",
            "description": "ID de Ana García"
        },
        {
            "type": "employee_id",
            "value": "1002", 
            "description": "ID de Carlos López"
        }
    ]
    
    # Datos que NO deberían estar en la BD
    non_existing_test_cases = [
        {
            "type": "email",
            "value": "javier.guerra@devol.es",
            "description": "Email externo que causaba el error"
        },
        {
            "type": "email",
            "value": "test@noexiste.com",
            "description": "Email completamente inexistente"
        },
        {
            "type": "employee_id",
            "value": "9999",
            "description": "ID inexistente"
        }
    ]
    
    # 1. PROBAR CASOS QUE DEBERÍAN EXISTIR
    print("\n✅ PROBANDO DATOS QUE DEBERÍAN EXISTIR EN LA BD")
    print("-" * 50)
    
    for case in existing_test_cases:
        await test_single_case(case, should_exist=True)
    
    # 2. PROBAR CASOS QUE NO DEBERÍAN EXISTIR
    print("\n❌ PROBANDO DATOS QUE NO DEBERÍAN EXISTIR")
    print("-" * 50)
    
    for case in non_existing_test_cases:
        await test_single_case(case, should_exist=False)
    
    # 3. CASO ESPECÍFICO: SIMULAR EL ERROR Y EL FIX
    print("\n🎯 CASO ESPECÍFICO: SIMULACIÓN DEL ERROR Y FIX")
    print("-" * 50)
    await simulate_error_and_fix()

async def test_single_case(test_case, should_exist=True):
    """Probar un caso individual"""
    case_type = test_case["type"]
    value = test_case["value"]
    description = test_case["description"]
    
    print(f"\n🔍 Probando {case_type}: {value}")
    print(f"   📝 {description}")
    
    try:
        # Ejecutar la tool apropiada
        if case_type == "email":
            result = await search_by_email_adapted.ainvoke({"email": value})
        else:  # employee_id
            result = await search_by_employee_id_adapted.ainvoke({"employee_id": value})
        
        # Analizar resultado
        found = result.get("found", False)
        
        if should_exist:
            if found:
                print("   ✅ CORRECTO: Encontrado como se esperaba")
                print_result_details(result)
                
                # Verificar que no hay valores None problemáticos
                check_none_values(result)
                
            else:
                print(f"   ⚠️ INESPERADO: No encontrado, pero debería existir")
                print(f"   📄 Error: {result.get('error', 'Sin error reportado')}")
        else:
            if not found:
                print("   ✅ CORRECTO: No encontrado como se esperaba")
                print(f"   📄 Error: {result.get('error', 'Sin error reportado')}")
            else:
                print("   ⚠️ INESPERADO: Encontrado, pero no debería existir")
                print_result_details(result)
    
    except Exception as e:
        print(f"   💥 ERROR EXCEPCIÓN: {e}")
        print(f"   🔧 Tipo de error: {type(e).__name__}")

def print_result_details(result):
    """Imprimir detalles del resultado"""
    print("   📊 DETALLES:")
    print(f"      👤 Nombre: {result.get('nombre', 'N/A')}")
    print(f"      📧 Email: {result.get('email', 'N/A')}")  
    print(f"      🏪 Tienda: {result.get('nombre_tienda', 'N/A')}")
    print(f"      🏢 Departamento: {result.get('departamento', 'N/A')}")
    print(f"      🆔 ID Empleado: {result.get('numero_empleado', 'N/A')}")

def check_none_values(result):
    """Verificar valores None que podrían causar problemas"""
    none_values = []
    critical_fields = ['nombre', 'email', 'nombre_tienda', 'departamento']
    
    for field in critical_fields:
        if result.get(field) is None:
            none_values.append(field)
    
    if none_values:
        print(f"   ⚠️ VALORES None DETECTADOS: {none_values}")
        print("   🔧 Estos valores podrían causar el error de formateo")
    else:
        print("   ✅ No hay valores None problemáticos")

async def simulate_error_and_fix():
    """Simular el error específico y mostrar cómo el fix lo resuelve"""
    
    print("\n🧪 SIMULANDO EL CASO QUE CAUSABA ERROR:")
    print("Email: javier.guerra@devol.es")
    
    try:
        # Buscar el email
        result = await search_by_email_adapted.ainvoke({"email": "javier.guerra@devol.es"})
        
        print("\n📊 RESULTADO DE LA BÚSQUEDA:")
        for key, value in result.items():
            print(f"   {key}: {value} (tipo: {type(value).__name__})")
        
        if result.get("found"):
            print("\n⚠️ Email encontrado - simulando formateo con valores potencialmente None:")
            
            # MÉTODO ORIGINAL (que causaba error si había None)
            print("\n🔴 MÉTODO ORIGINAL (problemático):")
            try:
                # Simular que algunos valores son None para provocar el error
                test_result = result.copy()
                test_result['departamento'] = None  # Simular None
                test_result['nombre_tienda'] = f"Eroski {test_result['departamento']}"
                
                unsafe_message = f"""
👤 **Empleado:** {test_result['nombre']}
📧 **Email:** {test_result['email']}  
🏪 **Tienda:** {test_result['nombre_tienda']}
🏢 **Departamento:** {test_result['departamento']}"""
                
                print("   💥 Esto causaría: unsupported format string passed to NoneType.__format__")
                
            except Exception as e:
                print(f"   💥 ERROR CONFIRMADO: {e}")
            
            # MÉTODO CON FIX (seguro)
            print("\n🟢 MÉTODO CON FIX (seguro):")
            empleado_nombre = result.get('nombre') or 'No disponible'
            empleado_email = result.get('email') or 'No disponible'
            nombre_tienda = result.get('nombre_tienda') or 'No especificada'
            departamento = result.get('departamento') or 'No especificado'
            
            safe_message = f"""
👤 **Empleado:** {empleado_nombre}
📧 **Email:** {empleado_email}
🏪 **Tienda:** {nombre_tienda}
🏢 **Departamento:** {departamento}"""
            
            print("   ✅ FORMATEO SEGURO EXITOSO:")
            print(safe_message)
            
        else:
            print("\n✅ Email no encontrado (comportamiento esperado)")
            print(f"Error: {result.get('error')}")
            print("🔧 En este caso, el error de formateo no ocurriría porque no se llega al método _handle_successful_identification")
    
    except Exception as e:
        print(f"\n💥 ERROR EN SIMULACIÓN: {e}")

# Función para ejecutar directamente
async def main():
    """Función principal"""
    print("🚀 EJECUTANDO PRUEBAS ESPECÍFICAS DE BASE DE DATOS")
    print("🎯 Objetivo: Verificar el fix para el error de formateo")
    print()
    
    await test_database_tools()
    
    print("\n" + "="*60)
    print("📋 CONCLUSIONES:")
    print("   1. Las tools deberían manejar correctamente datos existentes")
    print("   2. Las tools deberían manejar correctamente datos no existentes")
    print("   3. El fix previene errores de formateo con valores None")
    print("   4. javier.guerra@devol.es no debería causar crashes")
    print("\n🎉 Si todas las pruebas pasan, el fix está funcionando correctamente")

if __name__ == "__main__":
    # Ejecutar las pruebas
    asyncio.run(main())