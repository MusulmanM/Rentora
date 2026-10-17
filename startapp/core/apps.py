from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from . import signals  # noqa: F401
        from .net import prefer_ipv4

        prefer_ipv4()  # IPv6 to Telegram hangs on the server; see core/net.py
