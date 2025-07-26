
import sys
import os

# Añade la raíz del proyecto al sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class EroskiIncidentsManager:
    """Maneja la carga y búsqueda en el archivo JSON de incidencias frecuentes."""
    
    def __init__(self, json_path: str = "data/eroski_incidents.json"):
        self.json_path = Path(json_path)
        self.incidents_data = self._load_incidents()
    
    def _load_incidents(self) -> Dict[str, Any]:
        """Carga el archivo JSON de incidencias."""
        try:
            if not self.json_path.exists():
                logger.warning(f"Archivo de incidencias no encontrado: {self.json_path}")
                return {"incident_types": {}}
            
            with open(self.json_path, 'r', encoding='utf-8') as f:
                carga_datos = json.load(f)
                return carga_datos
        except Exception as e:
            logger.error(f"Error cargando incidencias: {e}")
            return {"incident_types": {}}


    
    def get_problemas_soluciones(self, incident_type: str, limit: int = None) -> List[str]:
        """
        Obtiene ejemplos de problemas frecuentes para un tipo de incidencia.
        
        Args:
            incident_type: Tipo de incidencia (ej: "balanza")
            limit: Número máximo de ejemplos
            
        Returns:
            List[str]: Lista de problemas frecuentes
        """
        try:
            incident_data = self.incidents_data.get("incident_types", {}).get(incident_type, {})
            #print("👹"*100)
            #print(f"👹incident_data: {incident_data} \nincident_type: {incident_type}")
            problemas = incident_data.get("problemas", {})
            #print(f"👹problemas: {problemas}")
            #print(f"👹problmeas_type: {type(problemas)}")
            
            return problemas
        except Exception as e:
            logger.error(f"Error obteniendo ejemplos: {e}")
            return []
    


    def get_ejemplos_frecuentes(self, incident_type: str, limit: int = None) -> List[str]:
        """
        Obtiene ejemplos de problemas frecuentes para un tipo de incidencia.
        
        Args:
            incident_type: Tipo de incidencia (ej: "balanza")
            limit: Número máximo de ejemplos
            
        Returns:
            List[str]: Lista de problemas frecuentes
        """
        try:
            incident_data = self.incidents_data.get("incident_types", {}).get(incident_type, {})
            #print("👹"*100)
            #print(f"👹incident_data: {incident_data} \nincident_type: {incident_type}")
            problemas = incident_data.get("problemas", {})
            #print(f"👹problemas: {problemas}")
            
            return list(problemas.keys())[:limit]
        except Exception as e:
            logger.error(f"Error obteniendo ejemplos: {e}")
            return []
    
    def buscar_solucion_json(self, incident_type: str, problema: str) -> Optional[Tuple[str, float]]:
        """
        Busca una solución en el JSON para un problema específico.
        
        Args:
            incident_type: Tipo de incidencia
            problema: Descripción del problema
            
        Returns:
            Tuple[str, float]: (solución, confidence) o None si no encuentra
        """
        try:
            incident_data = self.incidents_data.get("incident_types", {}).get(incident_type, {})
            problemas = incident_data.get("problemas", {})
            
            # Búsqueda exacta
            if problema in problemas:
                return problemas[problema], 1.0
            
            # Búsqueda por similitud de texto simple
            problema_lower = problema.lower()
            for key, solucion in problemas.items():
                if problema_lower in key.lower() or key.lower() in problema_lower:
                    # Calcular confidence básico basado en longitud de coincidencia
                    overlap = len(set(problema_lower.split()) & set(key.lower().split()))
                    total_words = len(set(problema_lower.split()) | set(key.lower().split()))
                    confidence = overlap / total_words if total_words > 0 else 0
                    
                    if confidence >= 0.5:
                        return solucion, confidence
            
            return None
        except Exception as e:
            logger.error(f"Error buscando en JSON: {e}")
            return None
        
    def get_info_adicional(self, incident_type: str) -> List[str]:
        """Devuelve la lista de campos de info_adicional para un tipo de incidencia"""
        try:
            return self.incidents_data.get("incident_types", {}).get(incident_type, {}).get("info_adicional", [])
        except Exception as e:
            logger.error(f"Error obteniendo info_adicional: {e}")
            return []
