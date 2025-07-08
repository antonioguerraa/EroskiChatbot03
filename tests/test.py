import asyncio
from nodes.identificador_base_de_datos import identificador_base_de_datos_node
from models.eroski_state import EroskiState
from langchain_core.messages import HumanMessage

async def interactive_loop():
    # Estado inicial vacío o con valores por defecto
    state = EroskiState(
        authenticated=False,
        email_authen_tried=False,
        employee_id_authent_tried=False,
        # otros campos según tu modelo
    )

    while True:
        # Ejecuta el nodo con el estado actual
        result = await identificador_base_de_datos_node(state)
        update = result.update  # dict con actualizaciones

        if update and "messages" in update:
            messages = update["messages"]  # lista de mensajes
            for msg in messages:
                # Si usas langchain_core.messages.AIMessage
                if hasattr(msg, "content"):
                    print("🤖:", msg.content)
                else:
                    print("🤖:", msg)
        else:
            print("No hay mensajes en la respuesta del nodo.")
        # Muestra resultado (ajusta según estructura de Command y estado)
        #print("🤖:", result)


        # Actualiza el estado con la respuesta (depende de cómo manejes el estado)
        # Aquí debes implementar cómo aplicar 'result' al 'state'
        # Por ejemplo, si result es un dict con actualizaciones:
        if isinstance(result, dict) and "update" in result:
            state.update(result["update"])

        # Condición de salida (por ejemplo, usuario autenticado)
        if state.get("authenticated", False):
            print("Usuario autenticado, terminando.")
            break

        # Solicita entrada del usuario para actualizar estado
        user_input = input("👹: ")
        if user_input.lower() == "salir":
            break

        # Actualiza estado con entrada del usuario (ajusta según tu modelo)
        # Ejemplo simple:
        state.update({
            "messages": [HumanMessage(content=user_input)]
        })

if __name__ == "__main__":
    asyncio.run(interactive_loop())
