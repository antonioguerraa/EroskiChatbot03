# 📋 EroskiState - Uso de Campos en el Flujo de Clasificación

| Categoría                | Campo                        | ¿Usado? | Descripción / Uso Actual                                    | Uso Sugerido Futuro                          |
|--------------------------|------------------------------|---------|-------------------------------------------------------------|----------------------------------------------|
| 🧑‍💼 Identificación       | `employee_name`              | ✅      | Usado en prompts y contexto                                 | –                                            |
|                          | `employee_email`             | ✅      | Para persistencia y seguimiento                             | –                                            |
|                          | `employee_id`                | ⚠️ No   | No utilizado                                                | Enlazar con SAP / sistemas internos          |
|                          | `authenticated`              | ✅      | Verifica que ha pasado la fase de autenticación             | –                                            |
|                          | `store_name`                 | ✅      | Contextualiza en prompts                                    | –                                            |
|                          | `store_id`                   | ⚠️ No   | No utilizado                                                | Filtrado o agregación en Power BI           |
|                          | `store_type`                 | ❌      | –                                                           | Inferir tipo de equipamiento prioritario     |
|                          | `department` (`section`)     | ✅      | Usado para inferir tipo de incidencia                       | –                                            |
|                          | `shift`                      | ❌      | –                                                           | Priorización por turno                       |
|                          | `employee_level`             | ⚠️ No   | No utilizado                                                | Escalabilidad por rol (ej. gerente ≠ empleado) |
| 💬 Conversación          | `messages`                   | ✅      | Historial completo usado por el LLM                         | Se persiste en `mensajes`                    |
|                          | `last_activity`              | ✅      | Actualizado en cada paso                                    | –                                            |
| 🧠 Clasificación         | `incident_type`              | ✅      | Resultado de Fase 1                                         | –                                            |
|                          | `incident_description`       | ✅      | Resultado de Fase 2 (con fallback)                          | Crítico para supervisores y resumen          |
|                          | `confidence_score`           | ✅      | Devuelto por Fase 1                                         | Umbral para escalar automáticamente          |
|                          | `query_type`                 | ⚠️ No   | No utilizado                                                | Diferenciar consultas de incidencias         |
|                          | `urgency_level`              | ❌      | –                                                           | Determinar prioridad en flujo                |
| 🔧 Solución              | `solution_found`             | ✅      | Se marca tras Fase 2                                        | –                                            |
|                          | `solution_content`           | ✅      | Se genera desde el catálogo                                 | –                                            |
|                          | `solution_type`              | ❌      | –                                                           | Manual / automática / guía paso a paso       |
|                          | `resolution_steps`           | ❌      | –                                                           | Mostrar pasos desglosados                    |
|                          | `automated_resolution`       | ❌      | –                                                           | Métricas de resolución automática            |
| 🚨 Escalación            | `needs_escalation`           | ✅      | Se marca en decisiones LLM o errores                        | –                                            |
|                          | `escalation_reason`          | ✅      | Visible en el mensaje al supervisor                         | –                                            |
|                          | `supervisor_id`              | ❌      | –                                                           | Asignación dinámica futura                   |
|                          | `escalation_contacts`        | ❌      | –                                                           | Email/Teléfono de contacto preferente        |
| 📨 Tickets               | `ticket_id`                  | ❌      | –                                                           | Integración con SAP                          |
|                          | `ticket_created`             | ❌      | –                                                           | Confirmación de creación                     |
|                          | `follow_up_needed`           | ❌      | –                                                           | Recordatorios programados                    |
|                          | `related_tickets`            | ❌      | –                                                           | Cluster de incidencias repetidas             |
| 🔄 Flujo de control      | `current_node`               | ✅      | `"classify"`, `"escalate"`, `"finalize"`                    | Crítico para LangGraph                       |
|                          | `attempts`                   | ⚠️ No   | No controlado explícitamente aún                            | Lógica de reintentos                         |
|                          | `max_attempts`               | ⚠️ No   | No usado                                                    | Umbral para escalar                          |
|                          | `can_retry`                  | ❌      | –                                                           | Para flujos fallidos                         |
|                          | `flow_completed`             | ✅      | Se marca al resolver                                        | –                                            |
|                          | `awaiting_user_input`        | ✅      | Se usa después de dar solución                              | –                                            |
| 📊 Métricas              | `resolved`                   | ✅      | Se marca cuando finaliza correctamente                      | –                                            |
|                          | `satisfaction_score`         | ❌      | –                                                           | Preguntar tras resolver                      |
|                          | `resolution_time_minutes`    | ❌      | –                                                           | Medir efectividad del asistente              |
| 🕒 Temporal              | `start_time`                 | ✅      | Se inicializa correctamente                                 | –                                            |
|                          | `end_time`                   | ⚠️ No   | No lo marcas al finalizar                                   | Cálculo de resolución                        |
| 🧠 Contexto y Debug      | `debug_info`                 | ⚠️ No   | Parcialmente usado                                          | Muy útil para trazabilidad y testing         |
|                          | `execution_path`             | ⚠️ No   | Se inicializa pero no se usa activamente                    | Diagnóstico de flujo                         |
|                          | `error_count`                | ⚠️ No   | No utilizado aún                                            | Escalación por errores consecutivos          |
| 📍 Otros útiles          | `incident_location`          | ❌      | –                                                           | Desambiguar ubicaciones en tienda            |
|                          | `error_codes`                | ❌      | –                                                           | En problemas técnicos con códigos            |

