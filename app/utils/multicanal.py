# app/utils/multicanal.py

from typing import Literal
from langchain_core.messages import AIMessage
from typing_extensions import TypedDict

# Define el tipo mínimo que necesitas del estado
class MinimalState(TypedDict, total=False):
    channel: Literal["whatsapp", "chainlit", "web"]

def renderizar_enlace(state: MinimalState, texto: str, url: str) -> str:
    """
    Devuelve un enlace adaptado al canal.
    - WhatsApp: 'Texto: https://url'
    - Otros: '[Texto](https://url)' (Markdown)
    """
    if state.get("channel") == "whatsapp":
        return f"{texto}: {url}"
    return f"[{texto}]({url})"

def formatear_texto(state: MinimalState, texto_plano: str, texto_markdown: str) -> str:
    """
    Devuelve texto adaptado al canal.
    - WhatsApp: texto plano
    - Otros: Markdown o texto enriquecido
    """
    return texto_plano if state.get("channel") == "whatsapp" else texto_markdown

def mensaje_adaptado(state: MinimalState, texto_plano: str, texto_markdown: str) -> AIMessage:
    """
    Devuelve un AIMessage con contenido adaptado al canal.
    """
    return AIMessage(content=formatear_texto(state, texto_plano, texto_markdown))
