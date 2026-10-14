"""Fill missing Russian/English listing copy with OpenAI, keeping provider-entered text untouched."""
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
TRANSLATED_FIELDS = ("title_ru", "title_en", "description_ru", "description_en")
_SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "string"} for name in TRANSLATED_FIELDS},
    "required": list(TRANSLATED_FIELDS),
    "additionalProperties": False,
}


def translation_enabled():
    return bool(getattr(settings, "OPENAI_API_KEY", ""))


def missing_translation_fields(listing):
    return [name for name in TRANSLATED_FIELDS if not getattr(listing, name, "").strip()]


def _request_translations(title, description):
    payload = {
        "model": getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You translate rental listings for Rentora, a home and car rental site in Uzbekistan. "
                    "The source text is usually Uzbek (it may also be Russian or English). "
                    "Translate the title and description into natural Russian and English. "
                    "Keep brand and model names (e.g. Chevrolet Cobalt, Audi R8) and numbers unchanged. "
                    "Use the standard Russian/English spelling of Uzbek places "
                    "(Toshkent → Ташкент / Tashkent, Chilonzor → Чиланзар / Chilanzar). "
                    "Keep line breaks. Do not add information that is not in the source."
                ),
            },
            {"role": "user", "content": json.dumps({"title": title, "description": description}, ensure_ascii=False)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "listing_translation", "strict": True, "schema": _SCHEMA},
        },
    }
    request = Request(
        _OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read())
    return json.loads(result["choices"][0]["message"]["content"])


def translate_listing(listing, save=True):
    """Fill empty RU/EN title and description fields. Returns the list of fields that were filled."""
    missing = missing_translation_fields(listing)
    if not missing or not translation_enabled():
        return []
    try:
        translated = _request_translations(listing.title, listing.description)
    except HTTPError as exc:
        logger.warning("Listing %s translation was rejected by OpenAI (HTTP %s).", listing.pk, exc.code)
        return []
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("Listing %s translation failed: %s", listing.pk, type(exc).__name__)
        return []
    except (ValueError, KeyError, IndexError, TypeError):
        logger.warning("Listing %s translation returned an invalid response.", listing.pk)
        return []

    filled = []
    for name in missing:
        value = str(translated.get(name, "")).strip()
        max_length = listing._meta.get_field(name).max_length
        if value:
            setattr(listing, name, value[:max_length] if max_length else value)
            filled.append(name)
    if filled and save and listing.pk:
        listing.save(update_fields=filled)
    return filled
