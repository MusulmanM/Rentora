"""Minimal Gemini tool-calling loop shared by the support AI and the admin assistant.

Tools are plain Python callables with a JSON schema. The model can only call the tools it is
given, so what an assistant may see is decided here in code, not by the prompt.
"""
import json
import logging
from urllib.error import HTTPError, URLError

from django.conf import settings

from .gemini import chat_completion

logger = logging.getLogger(__name__)


class AgentError(Exception):
    def __init__(self, message, quota_exhausted=False):
        self.quota_exhausted = quota_exhausted
        super().__init__(message)


class Tool:
    def __init__(self, name, description, parameters, function):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.function = function

    def spec(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.parameters,
        }}


def _post(payload):
    if not getattr(settings, "GEMINI_API_KEY", ""):
        raise AgentError("GEMINI_API_KEY sozlanmagan.", quota_exhausted=True)
    try:
        return chat_completion(payload, timeout=45)
    except HTTPError as exc:
        quota = exc.code == 429  # every model in the chain is out of quota
        logger.warning("Gemini agent request failed with HTTP %s%s.", exc.code, " (quota exhausted)" if quota else "")
        message = (
            "Gemini limiti tugagan. Birozdan keyin qayta urinib ko'ring." if quota
            else "AI xizmati so'rovni bajarmadi. Birozdan keyin qayta urinib ko'ring."
        )
        raise AgentError(message, quota_exhausted=quota or exc.code in (401, 403)) from None
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("Gemini agent connection failed: %s", type(exc).__name__)
        raise AgentError("AI xizmatiga ulanib bo'lmadi.") from None


def run_agent(system_prompt, conversation, tools, max_steps=6):
    """Run the model with tools until it produces a text answer. `conversation` is a list of chat messages."""
    tool_map = {tool.name: tool for tool in tools}
    messages = [{"role": "system", "content": system_prompt}, *conversation]
    for _ in range(max_steps):
        payload = {"messages": messages, "temperature": 0.3}
        if tools:
            payload["tools"] = [tool.spec() for tool in tools]
        result = _post(payload)
        try:
            message = result["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise AgentError("AI xizmatidan noto'g'ri javob olindi.") from None
        calls = message.get("tool_calls") or []
        if not calls:
            return (message.get("content") or "").strip()
        messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
        for call in calls:
            name = call.get("function", {}).get("name")
            tool = tool_map.get(name)
            try:
                arguments = json.loads(call.get("function", {}).get("arguments") or "{}")
                output = tool.function(**arguments) if tool else {"error": "unknown tool"}
            except (TypeError, ValueError) as exc:
                output = {"error": f"invalid arguments: {type(exc).__name__}"}
            messages.append({
                "role": "tool", "tool_call_id": call.get("id"),
                "content": json.dumps(output, ensure_ascii=False, default=str)[:12000],
            })
    raise AgentError("AI javobni yakunlay olmadi.")
