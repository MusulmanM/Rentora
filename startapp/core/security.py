"""Request throttling, login brute-force protection and security headers."""
import hashlib
import ipaddress
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.signals import user_login_failed
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.dispatch import receiver
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect, JsonResponse
from django.urls import reverse

LOGIN_FAILURE_LIMIT = 8
LOGIN_FAILURE_WINDOW = 15 * 60


def _from_trusted_proxy(remote):
    try:
        address = ipaddress.ip_address(remote)
    except ValueError:
        return False
    for network in getattr(settings, "CF_TRUSTED_PROXIES", ["127.0.0.1/32", "::1/128"]):
        try:
            if address in ipaddress.ip_network(network, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request):
    remote = request.META.get("REMOTE_ADDR", "") or "unknown"
    # Cloudflare Tunnel connects from this machine (or the Docker bridge) and names the visitor in
    # CF-Connecting-IP. The header is trusted only from those addresses, so a visitor cannot fake it.
    if _from_trusted_proxy(remote):
        visitor = request.META.get("HTTP_CF_CONNECTING_IP", "").strip()
        if visitor:
            return visitor
    # Our own reverse proxy (Caddy) sets X-Real-IP.
    if getattr(settings, "TRUST_X_REAL_IP", False):
        forwarded = request.META.get("HTTP_X_REAL_IP", "").strip()
        if forwarded:
            return forwarded
    return remote


def _key(scope, value):
    digest = hashlib.sha256(str(value).lower().encode("utf-8")).hexdigest()[:32]
    return f"rl:{scope}:{digest}"


def hit(scope, value, limit, window):
    """Count one event; return True when the caller is over the limit for this window."""
    key = _key(scope, value)
    if cache.add(key, 1, timeout=window):
        return False
    try:
        count = cache.incr(key)
    except ValueError:  # Expired between add() and incr().
        cache.set(key, 1, timeout=window)
        return False
    return count > limit


def is_limited(scope, value, limit):
    return (cache.get(_key(scope, value)) or 0) >= limit


def rate_limited(scope, limit, window, by="ip"):
    """View decorator: reject with 429 after `limit` requests per `window` seconds."""

    def decorator(view):
        def wrapped(request, *args, **kwargs):
            if request.method == "POST":
                identity = request.user.pk if by == "user" and request.user.is_authenticated else client_ip(request)
                if hit(scope, identity, limit, window):
                    message = "Juda ko'p so'rov yuborildi. Birozdan keyin qayta urinib ko'ring."
                    if request.headers.get("Accept", "").startswith("application/json") or request.path.startswith("/api/"):
                        return JsonResponse({"detail": message}, status=429)
                    return HttpResponse(message, status=429, content_type="text/plain; charset=utf-8")
            return view(request, *args, **kwargs)

        wrapped.__name__ = view.__name__
        wrapped.__doc__ = view.__doc__
        return wrapped

    return decorator


@receiver(user_login_failed)
def count_login_failure(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    hit("login-ip", client_ip(request), LOGIN_FAILURE_LIMIT * 3, LOGIN_FAILURE_WINDOW)
    username = (credentials or {}).get("username", "")
    if username:
        hit("login-user", username, LOGIN_FAILURE_LIMIT, LOGIN_FAILURE_WINDOW)


class SecurityMiddleware:
    """Blocks brute-forced logins and adds CSP/permissions headers to every response."""

    LOGIN_PATHS = ("/accounts/login/",)
    # Signed-in or one-time pages: never cached, never indexed by search engines.
    PRIVATE_PREFIXES = (
        "/helper/", "/chats/", "/my-bookings/", "/profile/", "/provider/", "/payments/", "/api/",
        "/help/chat/", "/accounts/password/", "/accounts/register/verify/", "/accounts/logout/",
    )
    PERMISSIONS_POLICY = (
        "camera=(), geolocation=(), microphone=(self), payment=(), usb=(), "
        "magnetometer=(), gyroscope=(), accelerometer=()"
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.admin_prefix = "/" + getattr(settings, "ADMIN_URL", "admin/").strip("/") + "/"
        self.login_paths = self.LOGIN_PATHS + (self.admin_prefix + "login/",)

    def __call__(self, request):
        canonical = self._canonical_redirect(request)
        if canonical:
            return canonical
        if request.method == "POST" and request.path in self.login_paths:
            username = request.POST.get("username", "")
            if is_limited("login-ip", client_ip(request), LOGIN_FAILURE_LIMIT * 3) or (
                username and is_limited("login-user", username, LOGIN_FAILURE_LIMIT)
            ):
                return HttpResponse(
                    "Kirish urinishlari juda ko'p. 15 daqiqadan keyin qayta urinib ko'ring.",
                    status=429, content_type="text/plain; charset=utf-8",
                )
        if request.path.startswith(self.admin_prefix) and not request.user.is_superuser:
            # Only the head admin may see that the Django admin exists; everyone else signs in
            # through the site's rate-limited login page or gets a plain 404.
            if request.user.is_authenticated:
                raise Http404
            return redirect_to_login(request.get_full_path(), reverse("login"))
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", self.PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Resource-Policy", "same-site")
        response.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        if request.path.startswith(settings.MEDIA_URL):
            # Uploaded files are data, never documents: block scripts even if one is opened directly.
            response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'"
            response["X-Content-Type-Options"] = "nosniff"
            if response.status_code == 200:
                # Upload names are random and never reused, so browsers may keep them for a year.
                response["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.path.startswith(self.admin_prefix):
            # Admin pages hold private data: never cache them or let search engines index them.
            response["Cache-Control"] = "no-store, private"
            response["X-Robots-Tag"] = "noindex, nofollow"
        else:
            response.setdefault("Content-Security-Policy", settings.CONTENT_SECURITY_POLICY)
            if request.path.startswith(self.PRIVATE_PREFIXES):
                response["Cache-Control"] = "no-store, private"
                response["X-Robots-Tag"] = "noindex, nofollow"
        if request.method == "HEAD":
            self._drop_head_body(response)
        return response

    @staticmethod
    def _drop_head_body(response):
        """A HEAD answer must have headers only. gunicorn sent the page body anyway, and Cloudflare
        Tunnel then read those leftover bytes as the next response on the kept-alive connection
        ("malformed HTTP status code") and answered 502."""
        if response.streaming:
            close = getattr(response, "close", None)
            response.streaming_content = []
            if close:
                close()
        else:
            response.setdefault("Content-Length", str(len(response.content)))
            response.content = b""

    @staticmethod
    def _canonical_redirect(request):
        """www.rentora.uz -> rentora.uz (one address per page for users and search engines)."""
        public = urlsplit(getattr(settings, "PUBLIC_SITE_URL", "") or "")
        host = request.META.get("HTTP_HOST", "").split(":")[0].lower()
        if public.hostname and host == f"www.{public.hostname}":
            return HttpResponsePermanentRedirect(f"{public.scheme}://{public.netloc}{request.get_full_path()}")
        return None
