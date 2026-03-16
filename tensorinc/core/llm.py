import logging

import httpx
import ollama as _ollama

from tensorinc.core.config import settings

log = logging.getLogger(__name__)

# Per-call timeout in seconds (covers slow Ollama or unresponsive host)
_TIMEOUT = 120


def is_available() -> bool:
    """Check if the Ollama server is reachable."""
    try:
        resp = httpx.get(f"{settings.ollama_host}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def chat(prompt: str, system: str | None = None) -> str:
    """Send a prompt to the local Ollama model and return the response text."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client = _ollama.Client(host=settings.ollama_host, timeout=_TIMEOUT)
    response = client.chat(model=settings.ollama_model, messages=messages)
    return response.message.content


def chat_json(prompt: str, system: str | None = None) -> str:
    """Same as chat but requests JSON output format."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client = _ollama.Client(host=settings.ollama_host, timeout=_TIMEOUT)
    response = client.chat(
        model=settings.ollama_model,
        messages=messages,
        format="json",
    )
    return response.message.content
