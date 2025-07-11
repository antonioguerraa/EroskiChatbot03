# ====================================================================
# PASO 1: Crear el archivo utils/confirmation_analyzer.py
# ====================================================================

# utils/confirmation_analyzer.py
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ConfirmationResult:
    type: str  # 'confirmed', 'rejected', 'partial', 'unclear'
    confidence: int  # 0-100
    interpretation: str
    needs_clarification: bool = False

class HybridConfirmationAnalyzer:
    def __init__(self):
        # Patrones de confirmación explícita
        self.EXPLICIT_YES = ["sí", "si", "correcto", "exacto", "confirmo"]
        self.EXPLICIT_NO = ["no", "incorrecto", "nada que ver", "no funciona"]
        
        # Patrones de éxito implícito
        self.SUCCESS_HIGH = ["funciona perfecto", "ya está", "resuelto", "perfecto", "gracias"]
        self.SUCCESS_MEDIUM = ["funciona mejor", "va mejor", "mejoró", "ahora va"]
        
        # Patrones de fallo implícito
        self.FAILURE_HIGH = ["sigue igual", "no funciona", "mismo problema", "nada ha cambiado"]
        self.FAILURE_MEDIUM = ["no está bien", "algo falla", "no del todo"]
    
    def analyze_confirmation(self, message: str) -> ConfirmationResult:
        message_lower = message.lower().strip()
        
        # 1. Confirmaciones explícitas (máxima prioridad)
        for word in self.EXPLICIT_YES:
            if word in message_lower:
                return ConfirmationResult(
                    type="confirmed",
                    confidence=100,
                    interpretation="Usuario confirmó explícitamente"
                )
        
        for word in self.EXPLICIT_NO:
            if word in message_lower:
                return ConfirmationResult(
                    type="rejected",
                    confidence=100,
                    interpretation="Usuario rechazó explícitamente"
                )
        
        # 2. Indicadores implícitos
        success_score = 0
        failure_score = 0
        
        # Calcular puntuaciones
        for word in self.SUCCESS_HIGH:
            if word in message_lower:
                success_score += 40
        
        for word in self.SUCCESS_MEDIUM:
            if word in message_lower:
                success_score += 25
        
        for word in self.FAILURE_HIGH:
            if word in message_lower:
                failure_score += 45
        
        for word in self.FAILURE_MEDIUM:
            if word in message_lower:
                failure_score += 25
        
        # 3. Determinar resultado
        if success_score >= 40 and success_score > failure_score:
            confidence = min(85, success_score + 10)
            return ConfirmationResult(
                type="confirmed",
                confidence=confidence,
                interpretation=f"Indicadores de éxito detectados",
                needs_clarification=confidence < 80
            )
        elif failure_score >= 40 and failure_score > success_score:
            confidence = min(90, failure_score + 10)
            return ConfirmationResult(
                type="rejected",
                confidence=confidence,
                interpretation=f"Indicadores de fallo detectados",
                needs_clarification=confidence < 80
            )
        else:
            return ConfirmationResult(
                type="unclear",
                confidence=30,
                interpretation="No se detectaron indicadores claros",
                needs_clarification=True
            )
