"""Chat completions through Gemini's OpenAI-compatible endpoint.

Free-tier Gemini keys have small per-model quotas (about 20 requests a day for some models) and
models are often briefly overloaded (HTTP 503). Every model has its own quota, so a request walks
a chain of models and remembers which ones are out of quota until their reset time.
"""
import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_RETRY_IN = re.compile(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def _exhausted_key(model):
    return f"gemini-exhausted:{model}"


def models():
    chain = [getattr(settings, "GEMINI_MODEL", ""), *getattr(settings, "GEMINI_FALLBACK_MODELS", [])]
    return list(dict.fromkeys(model for model in chain if model))


def _quota_reset_seconds(body):
    match = _RETRY_IN.search(body)
    if not match:
        return 60
    hours, minutes, seconds = match.groups()
    total = int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0)
    return int(min(max(total, 30), 6 * 3600))


def _send(payload, timeout):
    request = Request(
        settings.AI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.GEMINI_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def chat_completion(payload, timeout=30):
    """Return the parsed completion. Raises the last HTTPError/URLError/TimeoutError if every model failed."""
    chain = models()
    available = [model for model in chain if not cache.get(_exhausted_key(model))] or chain[:1]
    last_error = None
    for model in available:
        # Thinking is off: these are short structured tasks and it makes replies several times faster.
        body = {**payload, "model": model, "reasoning_effort": "none"}
        for _ in range(2):
            try:
                return _send(body, timeout)
            except HTTPError as exc:
                last_error = exc
                if exc.code == 400 and "reasoning_effort" in body:
                    body.pop("reasoning_effort")  # some models cannot switch thinking off
                    continue
                if exc.code == 429:
                    try:
                        detail = exc.read().decode("utf-8", "replace")
                    except OSError:
                        detail = ""
                    cache.set(_exhausted_key(model), True, _quota_reset_seconds(detail))
                logger.warning("Gemini model %s returned HTTP %s.", model, exc.code)
                if exc.code in (401, 403):
                    raise  # bad or revoked key: other models will not help
                break
            except (URLError, TimeoutError) as exc:
                last_error = exc
                logger.warning("Gemini model %s did not answer: %s", model, type(exc).__name__)
                break
    raise last_error
