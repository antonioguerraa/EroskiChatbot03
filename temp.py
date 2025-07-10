def identify_problem(self, user_message: str, incident_type: str) -> Dict[str, Any]:
       """
       Identifica el problema específico del usuario usando LLM con JSON estructurado.
       
       Args:
           user_message: Mensaje del usuario
           incident_type: Tipo de incidencia
           
       Returns:
           Dict con problema, solución, confidence, keywords, etc.
       """
       try:
           # Obtener ejemplos del JSON
           ejemplos = self.incidents_manager.get_ejemplos_frecuentes(incident_type, 5)
           ejemplos_text = "\n".join([f"• {ej}" for ej in ejemplos]) if ejemplos else "No hay ejemplos disponibles"
           
           # Formatear prompt
           formatted_prompt = self.prompt_template.format(
               user_message=user_message,
               incident_type=incident_type,
               ejemplos_text=ejemplos_text
           )
           
           # Invocar LLM
           logger.info(f"🤖 Identificando problema para {incident_type} con mensaje: {user_message[:100]}...")
           response = self.llm.invoke(formatted_prompt)
           
           logger.debug(f"📥 Respuesta cruda LLM: {response.content[:200]}...")
           
           # Parsear con parser robusto
           parsed_result = self.parser.parse(response.content)
           
           # Validar y convertir a ProblemIdentificationResult si es necesario
           if isinstance(parsed_result, dict):
               try:
                   result_model = ProblemIdentificationResult(**parsed_result)
                   # Convertir de vuelta a dict para compatibilidad
                   result = result_model.dict()
               except Exception as e:
                   logger.warning(f"Error validando modelo Pydantic: {e}")
                   # Usar resultado parseado con valores por defecto
                   result = self._ensure_required_fields(parsed_result)
           else:
               result = parsed_result.dict() if hasattr(parsed_result, 'dict') else parsed_result
           
+           # Inicializar fuente de la solución
+           solution_source = "Otros"  # Por defecto, generado por LLM
+           
           # Buscar solución en JSON si hay alta confidence y no se encontró ya
           if result.get("confidence", 0) >= 0.75 and not result.get("solucion"):
               json_result = self.incidents_manager.buscar_solucion_json(
                   incident_type, result["problema"]
               )
               if json_result:
                   solucion, _ = json_result
                   result["solucion"] = solucion
                   result["similar_a_ejemplo"] = True
+                   solution_source = "FAQ"
+           elif result.get("solucion") and result.get("similar_a_ejemplo"):
+               # Si ya tiene solución y es similar a ejemplo, viene del JSON
+               solution_source = "FAQ"
+           
+           # Agregar fuente de la solución al resultado
+           result["solution_source"] = solution_source
           
           logger.info(f"✅ Problema identificado: '{result['problema']}' (confidence: {result['confidence']:.2f})")
           
           return result