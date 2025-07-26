#!/usr/bin/env python3
"""
Tester interactivo para grafo de identificación de incidencias.
Requiere: workflow.py, eroski_state.py y nodos definidos en /nodes.
"""

import os
import sys
import asyncio
from datetime import datetime
from langchain_core.messages import HumanMessage, AIMessage

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.eroski_state import create_initial_eroski_state, EroskiState
from workflows.workflow import run_graph  # Importa la función del grafo

import logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S')


class InteractiveGrafoTester:
    def __init__(self):
        self.session_counter = 0
        self.state = self.create_new_session()

    def create_new_session(self) -> EroskiState:
        self.session_counter += 1
        session_id = f"test_session_{self.session_counter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return create_initial_eroski_state(session_id=session_id, timezone="Europe/Madrid")

    async def handle_input(self, user_input: str):
        if user_input.lower() in {"exit", "quit"}:
            return False
        elif user_input.lower() == "reset":
            self.state = self.create_new_session()
            print("🔄 Nueva sesión iniciada")
            return True
        elif user_input.lower() == "state":
            print("\n📊 Estado actual:")
            for k, v in self.state.items():
                if k != "messages":
                    print(f"{k}: {v}")
            return True

        # Agregar mensaje del usuario
        prev_len = len(self.state.get("messages", []))
        self.state["messages"] += [HumanMessage(content=user_input)]

        # Ejecutar el grafo
        result = await run_graph(self.state)
        self.state.update(result)

        # Mostrar respuestas nuevas
        new_messages = self.state["messages"][prev_len:]
        for m in new_messages:
            if isinstance(m, AIMessage):
                print("🤖 " + "—" * 50)
                print(m.content)
                print("—" * 50)

        # Mostrar campos clave
        campos = ["incident_user_name", "incident_last_name", "incident_id"]
        for campo in campos:
            if self.state.get(campo):
                print(f"🪐 {campo}: {self.state.get(campo)}")

        return True

    async def run(self):
        print("🧪 Tester interactivo del grafo de identificación")
        print("Comandos: 'exit' para salir, 'reset' para reiniciar, 'state' para ver estado\n")
        while True:
            user_input = input("\n👤 Tú: ").strip()
            if not await self.handle_input(user_input):
                break


async def main():
    tester = InteractiveGrafoTester()
    await tester.run()

if __name__ == "__main__":
    asyncio.run(main())
