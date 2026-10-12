from django.conf import settings


def ai_assistant(request):
    return {"ai_enabled": bool(getattr(settings, "OPENAI_API_KEY", ""))}
