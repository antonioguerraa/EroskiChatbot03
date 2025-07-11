    async def execute(self, state: EroskiState) -> Command:
        ...
        # Manejar confirmación pendiente
        if state.get("pending_confirmation", False):
            ...
            if isinstance(confirmation_update, Command):
                self._track_incident_state(state, confirmation_update.update)
                return Command(update={**base_update, **confirmation_update.update})
            else:
                self._track_incident_state(state, confirmation_update)
                return Command(update={**base_update, **confirmation_update})

        # Manejar evaluación de solución
        if state.get("solution_content") and not state.get("solution_found", False):
            evaluation_update = self._evaluar_solucion(state)
            self._track_incident_state(state, evaluation_update)
            return Command(update={**base_update, **evaluation_update})

        # Proceso principal de identificación de problemas
        if not state.get("problem_identified", False):
            ...
            if not last_message:
                response = self._mostrar_ejemplos_frecuentes(...)
                return Command(update={...})  # No hace falta track

            try:
                agent_response = self.agent.invoke({...})
                verifier = AgentOutputLLMVerifier()
                response_update = verifier.analyze(...)
                self._track_incident_state(state, response_update)
                return Command(update={**base_update, **response_update})

            except Exception as e:
                return Command(update={...})  # No hace falta track

        # Estado por defecto (no hay cambios relevantes)
        return Command(update=base_update)