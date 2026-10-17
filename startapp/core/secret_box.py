"""Encryption at rest for providers' payment credentials (Fernet: AES-128-CBC + HMAC-SHA256).

The key comes from PAYMENT_ENCRYPTION_KEY (falls back to SECRET_KEY). If the key changes, stored
credentials can no longer be read and providers have to enter them again; online payments for
them stop until then instead of failing in an unsafe way.
"""
import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _fernet(key_material):
    digest = hashlib.sha256(("rentora-payment-credentials:" + key_material).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _box():
    return _fernet(getattr(settings, "PAYMENT_ENCRYPTION_KEY", "") or settings.SECRET_KEY)


def encrypt(value):
    return _box().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def decrypt(token):
    if not token:
        return ""
    try:
        return _box().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        logger.error("A stored payment credential could not be decrypted (was PAYMENT_ENCRYPTION_KEY changed?).")
        return ""
