# =====================================================
# nodes/identificador_base_de_datos.py - Nodo de Identificación con PostgreSQL
# =====================================================
"""
Nodo de identificación de usuario mediante búsqueda en base de datos PostgreSQL.

RESPONSABILIDADES:
- Identificar usuario por email o número de empleado
- Consultar base de datos PostgreSQL con dos tools específicas
- Manejar flags de estado para evitar búsquedas repetidas
- Usar agente React para interactuar naturalmente con el usuario
- Integrar herramientas de confirmación inteligente

CARACTERÍSTICAS:
- Agente React con dos tools especializadas
- Gestión de flags para optimización de consultas
- Manejo robusto de errores de conexión
- Interacción conversacional natural
- Mapeo automático al estado de EroskiState
"""

from typing import Dict, Any
from langchain_core.tools import tool
import logging
import asyncpg
import re
from config.settings import get_settings


# =============================================================================
# TOOLS PARA BÚSQUEDA EN BASE DE DATOS
# =============================================================================

@tool
async def search_by_email(email: str) -> Dict[str, Any]:
    """
    Buscar empleado por email en la base de datos PostgreSQL.
    
    Args:
        email: Email del empleado a buscar
        
    Returns:
        Dict con los datos del empleado o información de error
    """
    logger = logging.getLogger("SearchByEmail")
    
    try:
        # Validar formato de email
        if not email or not isinstance(email, str):
            return {"found": False, "error": "Email no válido"}
        
        email = email.strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return {"found": False, "error": "Formato de email inválido"}
        
        # Obtener configuración de BD
        settings = get_settings()
        connection_string = settings.database.connection_string
        
        # Conectar y buscar
        conn = await asyncpg.connect(connection_string)
        
        try:
            result = await conn.fetchrow("""
                SELECT numero_empleado, nombre, apellido, email, 
                       tienda as nombre_tienda, departamento
                FROM usuarios 
                WHERE LOWER(email) = $1 AND estado = 'activo'
            """, email)
            
            if result:
                logger.info(f"✅ Empleado encontrado por email: {result['nombre']} {result['apellido']}")
                return {
                    "found": True,
                    "numero_empleado": result['numero_empleado'],
                    "nombre": f"{result['nombre']} {result['apellido']}",
                    "email": result['email'],
                    "nombre_tienda": result['nombre_tienda'],
                    "departamento": result['departamento']
                }
            else:
                logger.info(f"❌ No se encontró empleado con email: {email}")
                return {"found": False, "error": "Email no encontrado en la base de datos"}
                
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"❌ Error buscando por email {email}: {e}")
        return {"found": False, "error": f"Error de conexión: {str(e)}"}


@tool
async def search_by_employee_id(employee_id: str) -> Dict[str, Any]:
    """
    Buscar empleado por número de empleado en la base de datos PostgreSQL.
    
    Args:
        employee_id: Número de empleado a buscar
        
    Returns:
        Dict con los datos del empleado o información de error
    """
    logger = logging.getLogger("SearchByEmployeeId")
    
    try:
        # Validar número de empleado
        if not employee_id or not isinstance(employee_id, str):
            return {"found": False, "error": "Número de empleado no válido"}
        
        employee_id = employee_id.strip()
        if not employee_id.isdigit() and not employee_id.isalnum():
            return {"found": False, "error": "Formato de número de empleado inválido"}
        
        # Obtener configuración de BD
        settings = get_settings()
        connection_string = settings.database.connection_string
        
        # Conectar y buscar
        conn = await asyncpg.connect(connection_string)
        
        try:
            result = await conn.fetchrow("""
                SELECT numero_empleado, nombre, apellido, email, 
                       tienda as nombre_tienda, departamento
                FROM usuarios 
                WHERE numero_empleado = $1 AND estado = 'activo'
            """, employee_id)
            
            if result:
                logger.info(f"✅ Empleado encontrado por ID: {result['nombre']} {result['apellido']}")
                return {
                    "found": True,
                    "numero_empleado": result['numero_empleado'],
                    "nombre": f"{result['nombre']} {result['apellido']}",
                    "email": result['email'],
                    "nombre_tienda": result['nombre_tienda'],
                    "departamento": result['departamento']
                }
            else:
                logger.info(f"❌ No se encontró empleado con ID: {employee_id}")
                return {"found": False, "error": "Número de empleado no encontrado"}
                
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"❌ Error buscando por ID {employee_id}: {e}")
        return {"found": False, "error": f"Error de conexión: {str(e)}"}
