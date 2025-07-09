def _get_specific_problems_for_type(self, incident_type: str) -> str:
    """
    Obtener una muestra de hasta 3 problemas específicos y sus soluciones para un tipo de incidencia.
    """

    try:
        from config.incident_config import IncidentConfigLoader
        config_loader = IncidentConfigLoader()
        incident_types = config_loader.get_incident_types()

        incident_data = incident_types.get(incident_type)
        if not incident_data:
            self.logger.warning(f"⚠️ Tipo de incidencia '{incident_type}' no encontrado en la configuración")
            return f"• Problemas técnicos relacionados con {incident_type}"

        
        problemas = incident_data.get("problemas", {})
        if not isinstance(problemas, dict) or not problemas:
            self.logger.warning(f"⚠️ No hay problemas definidos para el tipo '{incident_type}'")
            return f"• Problemas técnicos relacionados con {incident_type}"

        # Seleccionar hasta 3 problemas como ejemplo
        formatted = []
        for i, (problema, solucion) in enumerate(problemas.items()):
            if i >= 3:
                break
            formatted.append(f"""**{problema}**  
Solución: {solucion}""")

        result = "\n\n".join(formatted)
        result += f"\n\n💡 Estos son solo algunos ejemplos comunes con el equipo **{incident_type}**. ¿Podrías describirme tu problema concreto?"

        return result

    except Exception as e:
        self.logger.error(f"❌ Error cargando catálogo de problemas: {e}")
        return f"• Problemas técnicos relacionados con {incident_type}"





    def _get_specific_problems_for_type(self, incident_type: str) -> str:
        """
        Obtener catálogo de problemas específicos para un tipo de incidencia
        
        Args:
            incident_type: Tipo de incidencia (ej: "balanza", "tpv", etc.)
            
        Returns:
            String formateado con los problemas específicos disponibles
        """
        
        # ✅ CARGAR DESDE CONFIGURACIÓN DE INCIDENCIAS
        try:
            print(f"🏅incident_type: {incident_type}")
            from config.incident_config import IncidentConfigLoader
            config_loader = IncidentConfigLoader()
            incident_types = config_loader.get_incident_types()
            print("🏅check 0")
            print(f"🏅incident_types: {incident_types}")
            if incident_type in incident_types:
                print("🏅check 1")
                incident_data = incident_types[incident_type]
                print("🏅check 1.1")
                print(f"🏅incident_data: {incident_data}")
                # Verificar si tiene estructura "problemas"
                if "problemas" in get_type_hints(type(incident_data)):
                    print("🏅check 2: ")
                    problems = incident_data["problemas"]
                    
                    # Formatear problemas para el prompt
                    formatted_problems = []
                    for problem_key, solution in problems.items():
                        print("🏅check 3")
                        formatted_problems.append(f"• **{problem_key}**")
                    
                    return "\n".join(formatted_problems)
                
                # Fallback: estructura antigua
                elif "description" in get_type_hints(type(incident_data)):
                    print("🏅check 4")
                    return f"• Problemas diversos relacionados con {incident_type}"
            print("🏅check 5")
            
            self.logger.warning(f"⚠️ No se encontraron problemas específicos para {incident_type}")
            return f"• Problemas técnicos relacionados con {incident_type}"
            
        except Exception as e:
            self.logger.error(f"❌ Error cargando catálogo de problemas: {e}")
            
            # ✅ FALLBACK: Catálogo hardcodeado básico
            fallback_problems = {
                "balanza": """• **No enciende**
    • **No imprime etiquetas**
    • **Las etiquetas salen en blanco**
    • **Error de calibración**
    • **Precio incorrecto en etiquetas**
    • **No lee códigos de barras**
    • **Pantalla borrosa o dañada**
    • **Problemas de conectividad**""",
                
                "tpv": """• **TPV no enciende**
    • **No lee tarjetas de crédito**
    • **Error en el cajón de efectivo**
    • **Problemas con el lector de códigos de barras**
    • **La pantalla táctil no responde**
    • **No imprime tickets**
    • **Error de comunicación con el servidor**""",
                
                "impresora": """• **No imprime documentos**
    • **Impresión borrosa o con líneas**
    • **Atasco de papel**
    • **Error de tinta o tóner**
    • **No reconoce el formato de papel**
    • **Problemas de conectividad**""",
                
                "red": """• **Sin conexión a internet**
    • **WiFi muy lento**
    • **No puede acceder a aplicaciones corporativas**
    • **Error de conexión intermitente**
    • **Problemas con VPN**""",
                
                "ordenador": """• **El ordenador no enciende**
    • **Pantalla azul o error del sistema**
    • **Muy lento al trabajar**
    • **No reconoce dispositivos USB**
    • **Problemas con aplicaciones específicas**""",
                
                "telefono": """• **No hay línea telefónica**
    • **No se escucha al otro lado**
    • **Problemas con extensiones internas**
    • **Error en el sistema de intercomunicación**"""
            }
            
        return fallback_problems.get(incident_type, f"• Problemas técnicos relacionados con {incident_type}")



















Campo	Tipo	¿Dónde se usa?	Descripción
incident_code	str	Nodo	ID único generado por IncidentCodeManager
messages	list	Nodo / Prompt	Historial de mensajes (HumanMessage / AIMessage)
incident_type	str	Fase 1	Tipo de equipo identificado
problem_description	str	Fase 2	Descripción textual del problema
specific_problem	str	Fase 2	Problema del catálogo
proposed_solution	str	Fase 2	Solución recomendada del catálogo
confidence_score	float	Fase 1 / 2	Nivel de certeza del LLM
current_step	str	Nodo / grafo	Estado del nodo: classify, verify_solution, escalate, etc.
conversation_ended	bool	Nodo	Señal de cierre de conversación
error_occurred	bool	_handle_error	Si ha fallado algo en el flujo
auth_data_collected	dict	Prompt	Información del empleado (nombre, tienda, sección)
classify_data	dict	Fase 2	Info avanzada de clasificación (progreso, keywords, loop, etc.)
