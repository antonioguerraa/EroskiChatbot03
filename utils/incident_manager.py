# =====================================================
# utils/incident_manager.py - Gestor de Incidencias para buscar_solucion_node
# =====================================================
"""
Clase externa para gestionar incidencias específicamente desde buscar_solucion_node.py
después de que se haya identificado el tipo de incidencia.

RESPONSABILIDADES:
- Apertura de incidencia en primera llamada desde buscar_solucion_node
- Actualización del estado de soluciones
- Persistencia en JSON
- Cierre automático de incidencia
- Tracking completo del flujo de solución

FLUJO:
identificacion_incidencia_node → buscar_solucion_node → IncidentManager
"""

import json
import random
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass

from models.eroski_state import EroskiState


# =============================================================================
# CONFIGURACIÓN Y MODELOS
# =============================================================================

@dataclass
class IncidentConfig:
    """Configuración del gestor de incidencias"""
    database_file: Path = Path("incidents_database.json")
    auto_create: bool = True
    backup_enabled: bool = True
    log_level: str = "INFO"


class IncidentStatus:
    """Estados posibles de una incidencia"""
    ABIERTA = "abierta"
    EN_PROGRESO = "en_progreso"
    PENDIENTE_USUARIO = "pendiente_usuario"
    RESUELTA = "resuelta"
    ESCALADA = "escalada"
    CERRADA = "cerrada"


# =============================================================================
# GESTOR PRINCIPAL
# =============================================================================

class IncidentManager:
    """
    Gestor de incidencias específico para buscar_solucion_node.py
    
    USO TÍPICO:
    ```python
    # En buscar_solucion_node.py, al inicio del execute():
    from utils.incident_manager import get_incident_manager
    
    incident_manager = get_incident_manager()
    incident_id = incident_manager.manage_incident(state)
    # Continuar con lógica normal del nodo...
    ```
    """
    
    def __init__(self, config: Optional[IncidentConfig] = None):
        self.config = config or IncidentConfig()
        self.logger = logging.getLogger("IncidentManager")
        self.logger.setLevel(getattr(logging, self.config.log_level))
        
        # Asegurar que el archivo existe
        if self.config.auto_create:
            self._ensure_database_exists()
    
    # =========================================================================
    # MÉTODO PRINCIPAL - LLAMADA DESDE buscar_solucion_node.py
    # =========================================================================
    
    def manage_incident(self, state: EroskiState) -> Optional[str]:
        """
        🎯 MÉTODO PRINCIPAL - Gestionar incidencia desde buscar_solucion_node.
        
        En la primera llamada:
        - Abre nueva incidencia con datos completos
        - Valida que venga de identificacion_incidencia (incident_type existe)
        
        En llamadas posteriores:
        - Actualiza estado de solución
        - Cierra incidencia si está resuelta
        
        Args:
            state: Estado actual de buscar_solucion_node
            
        Returns:
            ID de la incidencia (ER-XXXX) o None si error
        """
        try:
            # Verificar que tenemos tipo de incidencia identificado
            if not state.get("incident_type"):
                self.logger.warning("⚠️ No hay incident_type. Debe venir de identificacion_incidencia_node")
                return None
            
            incident_id = state.get("incident_id")
            
            # Primera llamada: Abrir incidencia
            if not incident_id:
                incident_id = self._open_solution_incident(state)
                if incident_id:
                    self.logger.info(f"🆕 Incidencia abierta: {incident_id}")
                return incident_id
            
            # Llamadas posteriores: Actualizar estado
            else:
                self._update_solution_progress(incident_id, state)
                self.logger.info(f"🔄 Incidencia actualizada: {incident_id}")
                
                # Cerrar si está resuelta o escalada
                if self._should_close_incident(state):
                    self._close_solution_incident(incident_id, state)
                    self.logger.info(f"✅ Incidencia cerrada: {incident_id}")
                
                return incident_id
                
        except Exception as e:
            self.logger.error(f"❌ Error gestionando incidencia: {e}")
            return None
    
    # =========================================================================
    # APERTURA DE INCIDENCIAS DESDE BUSCAR_SOLUCION
    # =========================================================================
    
    def _open_solution_incident(self, state: EroskiState) -> Optional[str]:
        """Abrir nueva incidencia con datos completos desde buscar_solucion_node"""
        try:
            # Verificar datos necesarios
            if not self._has_required_data(state):
                self.logger.warning("⚠️ No hay datos suficientes para abrir incidencia")
                return None
            
            # Generar ID único
            incident_id = self._generate_unique_id()
            
            # Crear registro completo de incidencia
            incident_record = self._create_solution_incident_record(state, incident_id)
            
            # Guardar
            if self._save_incident(incident_id, incident_record):
                self.logger.info(f"🆕 Incidencia de solución abierta: {incident_id}")
                return incident_id
            else:
                self.logger.error("❌ Error guardando nueva incidencia")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Error abriendo incidencia de solución: {e}")
            return None
    
    def _create_solution_incident_record(self, state: EroskiState, incident_id: str) -> Dict[str, Any]:
        """Crear registro completo de incidencia desde buscar_solucion_node"""
        now = datetime.now()
        
        return {
            # Identificación
            "codigo_incidencia": incident_id,
            "timestamp_creacion": now.isoformat(),
            "estado": IncidentStatus.EN_PROGRESO,
            #"nodo_origen": "buscar_solucion",
            
            # Datos del empleado (desde identificador_manual)
            "nombre_empleado": self._extract_employee_name(state),
            #"email_empleado": self._extract_employee_email(state),
            "nombre_tienda": self._extract_store_name(state),
            "seccion": self._extract_department(state),
            #"numero_empleado": state.get("employee_id", ""),
            "empleado_autenticado": state.get("authenticated", False),
            
            # Datos de incidencia (desde identificacion_incidencia)
            "tipo_incidencia": state.get("incident_type"),
            "informacion_adicional":state.get("incident_info_adicional"),
            "descripcion_problema": state.get("incident_description"),
            "problema_especifico": state.get("problem_description"),
            #"confianza_identificacion": state.get("identification_confidence"),
            #"fuente_identificacion": state.get("identification_source"),
            #"detalles_adicionales": state.get("incident_details", {}),
            
            # Estado inicial de solución
            "solucion_encontrada": False,
            #"tipo_solucion": None,
            "contenido_solucion": None,
            "escalacion_necesaria": False,
            #"razon_escalacion": None,
            
            # Tracking
            "conversacion": self._extract_messages(state),
            "session_id": state.get("session_id"),
            #"ultimo_nodo": "buscar_solucion",
            "timestamp_actualizacion": now.isoformat(),
            
            # Metadatos
            "version_sistema": "1.0",
            #"flujo_seguido": ["identificador_manual", "identificacion_incidencia", "buscar_solucion"]
        }
    
    def _has_required_data(self, state: EroskiState) -> bool:
        """Verificar que tenemos datos mínimos requeridos"""
        required_checks = [
            state.get("incident_type"),  # Debe venir de identificacion_incidencia
            self._extract_employee_name(state),  # Debe venir de identificador_manual
            self._extract_store_name(state) or self._extract_department(state)  # Al menos uno
        ]
        
        return all(required_checks)
    
    # =========================================================================
    # ACTUALIZACIÓN DE PROGRESO DE SOLUCIÓN
    # =========================================================================
    
    def _update_solution_progress(self, incident_id: str, state: EroskiState):
        """Actualizar progreso de búsqueda/aplicación de solución"""
        updates = {
            "informacion_adicional":state.get("incident_info_adicional"),
            "descripcion_problema": state.get("incident_description"),
            "problema_especifico": state.get("problem_description"),
            "solucion_encontrada": state.get("solution_found", False),
            "tipo_solucion": state.get("solution_type"),
            "contenido_solucion": state.get("solution_content"),
            "escalacion_necesaria": state.get("escalation_needed", False),
            "razon_escalacion": state.get("escalation_reason"),
            "conversacion": self._extract_messages(state),
            "timestamp_actualizacion": datetime.now().isoformat()
        }
        
        # Actualizar estado según progreso
        if state.get("solution_found"):
            updates["estado"] = IncidentStatus.PENDIENTE_USUARIO
        elif state.get("escalation_needed"):
            updates["estado"] = IncidentStatus.ESCALADA
        
        self._update_incident(incident_id, updates)
    
    def _should_close_incident(self, state: EroskiState) -> bool:
        """Determinar si la incidencia debe cerrarse"""
        return (
            state.get("solution_found") and 
            state.get("awaiting_solution_confirmation") == False
        ) or (
            state.get("escalation_needed") and 
            state.get("escalation_level") in ["technical", "supervisor"]
        )
    
    def _close_solution_incident(self, incident_id: str, state: EroskiState):
        """Cerrar incidencia con razón específica"""
        if state.get("solution_found"):
            close_reason = "solucion_aplicada"
            final_status = IncidentStatus.RESUELTA
        elif state.get("escalation_needed"):
            close_reason = "escalada_a_supervisor"
            final_status = IncidentStatus.ESCALADA
        else:
            close_reason = "proceso_completado"
            final_status = IncidentStatus.CERRADA
        
        updates = {
            "estado": final_status,
            "razon_cierre": close_reason,
            "timestamp_cierre": datetime.now().isoformat(),
            "conversacion_final": self._extract_messages(state)
        }
        
        self._update_incident(incident_id, updates)
    
    # =========================================================================
    # EXTRACCIÓN INTELIGENTE DE DATOS
    # =========================================================================
    
    def _extract_employee_name(self, state: EroskiState) -> str:
        """Extraer nombre del empleado con fallbacks"""
        return (
            state.get("incident_user_name") or 
            state.get("employee_name") or
            state.get("auth_data_collected", {}).get("name") or
            ""
        )
    
    def _extract_employee_email(self, state: EroskiState) -> str:
        """Extraer email del empleado con fallbacks"""
        return (
            state.get("employee_email") or
            state.get("auth_data_collected", {}).get("email") or
            ""
        )
    
    def _extract_store_name(self, state: EroskiState) -> str:
        """Extraer nombre de tienda con fallbacks"""
        return (
            state.get("incident_store_name") or
            state.get("store_name") or
            state.get("auth_data_collected", {}).get("store_name") or
            ""
        )
    
    def _extract_department(self, state: EroskiState) -> str:
        """Extraer departamento con fallbacks"""
        return (
            state.get("incident_department") or
            state.get("department") or
            state.get("auth_data_collected", {}).get("section") or
            ""
        )
    
    def _extract_messages(self, state: EroskiState) -> List[Dict]:
        """Extraer y serializar mensajes de conversación"""
        messages = state.get("messages", [])
        serialized = []
        
        for msg in messages[-10:]:  # Solo últimos 10 mensajes
            try:
                msg_dict = {
                    "type": msg.__class__.__name__,
                    "content": msg.content,
                    "timestamp": datetime.now().isoformat()
                }
                serialized.append(msg_dict)
            except Exception as e:
                self.logger.warning(f"⚠️ Error serializando mensaje: {e}")
        
        return serialized
    
    # =========================================================================
    # PERSISTENCIA
    # =========================================================================
    
    def _update_incident(self, incident_id: str, updates: Dict[str, Any]) -> bool:
        """Actualizar incidencia existente"""
        try:
            incidents_data = self._load_incidents()
            
            if incident_id not in incidents_data:
                self.logger.warning(f"⚠️ Incidencia {incident_id} no encontrada")
                return False
            
            # Actualizar datos
            incidents_data[incident_id].update(updates)
            
            # Guardar
            if self._save_incidents(incidents_data):
                self.logger.debug(f"✅ Incidencia {incident_id} actualizada: {list(updates.keys())}")
                return True
            else:
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error actualizando incidencia {incident_id}: {e}")
            return False
    
    def _save_incident(self, incident_id: str, record: Dict[str, Any]) -> bool:
        """Guardar nueva incidencia"""
        try:
            incidents_data = self._load_incidents()
            incidents_data[incident_id] = record
            return self._save_incidents(incidents_data)
        except Exception as e:
            self.logger.error(f"❌ Error guardando incidencia {incident_id}: {e}")
            return False
    
    def _load_incidents(self) -> Dict[str, Any]:
        """Cargar incidencias del archivo JSON"""
        try:
            if self.config.database_file.exists():
                with open(self.config.database_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.error(f"❌ Error cargando incidencias: {e}")
            return {}
    
    def _save_incidents(self, data: Dict[str, Any]) -> bool:
        """Guardar incidencias al archivo JSON"""
        try:
            # Backup si está habilitado
            if self.config.backup_enabled and self.config.database_file.exists():
                backup_file = self.config.database_file.with_suffix('.backup.json')
                import shutil
                shutil.copy2(self.config.database_file, backup_file)
            
            # Guardar
            with open(self.config.database_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            self.logger.error(f"❌ Error guardando incidencias: {e}")
            return False
    
    # =========================================================================
    # UTILIDADES
    # =========================================================================
    
    def _generate_unique_id(self) -> str:
        """Generar ID único formato ER-NNNN"""
        existing_ids = set(self._load_incidents().keys())
        
        for _ in range(1000):
            incident_id = f"ER-{random.randint(1000, 9999)}"
            if incident_id not in existing_ids:
                return incident_id
        
        # Fallback
        return f"ER-{random.randint(10000, 99999)}"
    
    def _has_employee_data(self, state: EroskiState) -> bool:
        """Verificar si hay datos mínimos del empleado (legacy - mantenido para compatibilidad)"""
        return self._has_required_data(state)
    
    def _ensure_database_exists(self):
        """Asegurar que el archivo de base de datos existe"""
        if not self.config.database_file.exists():
            self.config.database_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config.database_file, 'w', encoding='utf-8') as f:
                json.dump({}, f)
            self.logger.info(f"✅ Archivo de incidencias creado: {self.config.database_file}")
    
    # =========================================================================
    # MÉTODOS DE CONVENIENCIA
    # =========================================================================
    
    def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Obtener incidencia por ID"""
        incidents = self._load_incidents()
        return incidents.get(incident_id)
    
    def list_incidents(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Listar incidencias, opcionalmente filtradas por estado"""
        incidents = self._load_incidents()
        result = []
        
        for incident_id, data in incidents.items():
            if status is None or data.get("estado") == status:
                result.append({"id": incident_id, **data})
        
        return result
    
    def close_incident(self, incident_id: str, reason: str = "completada") -> bool:
        """Cerrar incidencia"""
        return self._update_incident(incident_id, {
            "estado": IncidentStatus.CERRADA,
            "razon_cierre": reason,
            "timestamp_cierre": datetime.now().isoformat()
        }, "system")


# =============================================================================
# FACTORY Y SINGLETON
# =============================================================================

_incident_manager_instance = None

def get_incident_manager(config: Optional[IncidentConfig] = None) -> IncidentManager:
    """Factory para obtener instancia singleton del gestor"""
    global _incident_manager_instance
    
    if _incident_manager_instance is None:
        _incident_manager_instance = IncidentManager(config)
    
    return _incident_manager_instance


# =============================================================================
# EJEMPLO DE USO
# =============================================================================

if __name__ == "__main__":
    # Ejemplo de uso desde un nodo
    from models.eroski_state import EroskiState
    
    # Estado de ejemplo
    state = EroskiState({
        # Datos del empleado (desde identificador_manual)
        "employee_name": "Juan Pérez",
        "incident_store_name": "Eroski Bilbao Centro",
        "incident_department": "Carnicería",
        "authenticated": True,
        
        # Datos de identificación (desde identificacion_incidencia)
        "incident_type": "balanza",
        "incident_description": "Problema con la balanza de carnicería",
        "identification_confidence": 0.85,
        
        # Datos de solución (desde buscar_solucion - primera llamada)
        "solution_found": False,
        "solution_content": None,
        "messages": []
    })
    
    # Primera llamada: Abrir incidencia
    manager = get_incident_manager()
    incident_id = manager.manage_incident(state)
    print(f"✅ Incidencia abierta: {incident_id}")
    
    # Simular progreso de solución
    state.update({
        "incident_id": incident_id,
        "solution_found": True,
        "solution_content": "Reiniciar la balanza y recalibrar",
        "solution_type": "procedimiento_tecnico"
    })
    
    # Segunda llamada: Actualizar con solución
    manager.manage_incident(state)
    print("✅ Incidencia actualizada con solución")
    
    # Verificar estado final
    incident = manager.get_incident(incident_id)
    print(f"📋 Estado final: {incident['estado']}")
    print(f"🔧 Solución: {incident['contenido_solucion']}")
    print(f"👤 Empleado: {incident['nombre_empleado']}")
    print(f"🏪 Tienda: {incident['nombre_tienda']}")
    print(f"⚡ Tipo: {incident['tipo_incidencia']}")