# 📋 EroskiState - Campos Usados en el Nodo `identificacion_manual.py`

Este documento enumera los campos del estado `EroskiState` que son utilizados específicamente en el nodo de identificación manual mediante LLM.

| Categoría             | Campo (`EroskiState`)       | ¿Usado? | ¿Dónde se usa? |
|----------------------|------------------------------|---------|----------------|
| 🧑‍💼 Identificación   | `employee_name`              | ✅      | Recogido desde el mensaje del usuario (`nombre`) |
|                      | `employee_id`                | ✅      | Extraído como `numero_empleado` |
|                      | `incident_store_name`        | ✅      | Recogido como `tienda` |
|                      | `incident_department`        | ✅      | Recogido como `seccion` |
|                      | `store_id`                   | ✅      | Asignado tras confirmar tienda (código de tienda) |
|                      | `authenticated`              | ✅      | Marcado al finalizar identificación |
|                      | `identification_complete`    | ✅      | Marcado al completar todos los datos |
|                      | `manual_identification_completed` | ✅ | Marcado al completar identificación por LLM |
| 💬 Conversación      | `messages`                   | ✅      | Se actualiza en cada interacción con el usuario |
| 🔄 Flujo             | `current_node`               | ✅      | Se actualiza como `"identificacion_manual"` |
|                      | `pending_store_confirmation` | ✅      | Almacena sugerencia y estado de confirmación de tienda |
|                      | `pending_section_confirmation`| ✅     | Almacena sugerencia y estado de confirmación de sección |
|                      | `pending_store_selection`    | ✅      | Cuando el usuario debe seleccionar manualmente la tienda |
|                      | `identification_started`     | ✅      | Marcado al iniciar la conversación |
| ⚠️ Errores           | `error_count`                | ✅      | Se incrementa al fallar el proceso |
|                      | `identification_error`       | ✅      | Guarda mensaje de error en caso de fallo |

---

## ❌ Campos NO utilizados en este nodo

Este nodo no usa campos relacionados con:

- Clasificación de incidencias (`incident_type`, `incident_description`, etc.)
- Soluciones (`solution_content`, `solution_found`, etc.)
- Escalación técnica (`escalation_reason`, `needs_escalation`, etc.)
- Tickets y seguimiento (`ticket_id`, `follow_up_needed`, etc.)
- Métricas (`satisfaction_score`, `resolution_time_minutes`, etc.)
- Debug (`execution_path`, `debug_info`, etc.)

