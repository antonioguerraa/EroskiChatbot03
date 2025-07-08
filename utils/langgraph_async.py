from langgraph.graph import StateGraph
from langgraph.types import Command
from models.eroski_state import EroskiState

def wrap_async_node(async_func):
    class AsyncNode:
        async def invoke(self, state: EroskiState) -> Command:
            return await async_func(state)
    return AsyncNode()
