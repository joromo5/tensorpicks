import ollama as _ollama

from tensorpicks.core.config import settings


def chat(prompt: str, system: str | None = None) -> str:
    """Send a prompt to the local Ollama model and return the response text."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client = _ollama.Client(host=settings.ollama_host)
    response = client.chat(model=settings.ollama_model, messages=messages)
    return response.message.content


def chat_json(prompt: str, system: str | None = None) -> str:
    """Same as chat but requests JSON output format."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client = _ollama.Client(host=settings.ollama_host)
    response = client.chat(
        model=settings.ollama_model,
        messages=messages,
        format="json",
    )
    return response.message.content
