# 📋 EroskiState - Campos Usados en el Nodo `identificador_base_de_datos.py`

Este documento enumera los campos del estado `EroskiState` que son utilizados específicamente en el nodo de identificación mediante base de datos PostgreSQL.

| Categoría             | Campo (`EroskiState`)       | ¿Usado? | ¿Dónde se usa? |
|----------------------|------------------------------|---------|----------------|
| 🧑‍💼 Identificación   | `employee_name`              | ✅      | Guardado desde BD en `_handle_successful_identification` |
|                      | `employee_email`             | ✅      | Guardado desde BD y usado para evitar reintentos |
|                      | `employee_id`                | ✅      | Guardado desde `numero_empleado` |
|                      | `store_name`                 | ✅      | Guardado desde `nombre_tienda` |
|                      | `department`                 | ✅      | Guardado desde `departamento` |
|                      | `authenticated`              | ✅      | Comprobado al entrar al nodo, marcado al identificar |
|                      | `email_authen_tried`         | ✅      | Flag para evitar repetición de búsqueda por email |
|                      | `employee_id_authent_tried`  | ✅      | Flag para evitar repetición por número de empleado |
|                      | `identification_method`      | ✅      | Se guarda como `"database"` si se identifica correctamente |
|                      | `identification_failed`      | ✅      | Se marca como `True` si ambos métodos fallan |
| 💬 Conversación      | `messages`                   | ✅      | Historial de conversación, se añade cada respuesta |
| 🔄 Flujo             | `current_node`               | ✅      | Actualizado en cada paso como `"identificador_base_datos"` |
|                      | `last_activity`              | ✅      | Actualizado en cada punto de cambio de estado |
|                      | `awaiting_user_input`        | ✅      | Se activa al pedir datos o mostrar errores |
| ⚠️ Errores           | `error_occurred`             | ✅      | Se marca en `_handle_error()` |
|                      | `error_details`              | ✅      | Detalle del error técnico ocurrido |
| 🚨 Escalación        | `escalation_needed`           | ✅      | Si no se puede identificar o hay error crítico |
|                      | `escalation_reason`          | ✅      | Texto como `"Usuario no encontrado"` o por error técnico |
| 🧪 Confirmación (op.)| `pending_identification_data`| ⚠️ Opcional | Si se usa herramienta de confirmación externa |
| 🧩 Custom            | `identification_stage`       | ⚠️ Custom | `"requesting_credentials"` al iniciar interacción |

---

## ❌ Campos NO utilizados en este nodo

Este nodo no usa campos relacionados con:

- Clasificación (`incident_type`, `incident_description`, etc.)
- Soluciones (`solution_content`, `solution_found`, etc.)
- Tickets y seguimiento (`ticket_id`, `follow_up_needed`, etc.)
- Métricas (`satisfaction_score`, `resolution_time_minutes`, etc.)
- Debug (`execution_path`, `debug_info`, etc.)

