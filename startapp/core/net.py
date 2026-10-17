"""Prefer IPv4 for outgoing connections (Telegram, Gemini, Click).

On the production server IPv6 to api.telegram.org sometimes black-holes: a connection hangs for the
whole timeout before Python falls back to IPv4, so the bot answered after ~30 seconds. Normally
/etc/gai.conf would fix this, but the app runs without root, so the address order is changed here:
IPv4 addresses are tried first and IPv6 stays as a fallback.
"""
import socket

_original_getaddrinfo = socket.getaddrinfo


def _ipv4_first(*args, **kwargs):
    results = _original_getaddrinfo(*args, **kwargs)
    return sorted(results, key=lambda item: item[0] != socket.AF_INET)


def prefer_ipv4():
    if socket.getaddrinfo is not _ipv4_first:
        socket.getaddrinfo = _ipv4_first
