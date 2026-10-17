"""Search-engine and security metadata: robots.txt, sitemap.xml, security.txt."""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from .availability import listings_visible_to


def site_url(request):
    return (getattr(settings, "PUBLIC_SITE_URL", "") or request.build_absolute_uri("/")).rstrip("/")


class StaticPagesSitemap(Sitemap):
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return ["home", "register", "contact-admin"]

    def location(self, item):
        return reverse(item)


class ListingSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8
    limit = 5000

    def items(self):
        return listings_visible_to(AnonymousUser()).order_by("-created_at")

    def location(self, listing):
        return reverse("listing-detail", args=[listing.slug])

    def lastmod(self, listing):
        return listing.created_at


SITEMAPS = {"pages": StaticPagesSitemap, "listings": ListingSitemap}

# Private or per-user pages that search engines must not crawl. The secret admin address is left
# out on purpose: robots.txt is public, and those pages already send "X-Robots-Tag: noindex".
_DISALLOWED = (
    "/helper/", "/chats/", "/my-bookings/", "/profile/", "/provider/", "/payments/", "/api/",
    "/help/chat/", "/accounts/password/", "/telegram/",
)


@require_GET
@cache_page(60 * 60)
def robots_txt(request):
    lines = ["User-agent: *", *(f"Disallow: {path}" for path in _DISALLOWED), "", f"Sitemap: {site_url(request)}/sitemap.xml", ""]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def security_txt(request):
    expires = (timezone.now() + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
    body = "\n".join([
        f"Contact: {site_url(request)}{reverse('guest-support')}",
        f"Expires: {expires}",
        "Preferred-Languages: uz, ru, en",
        f"Canonical: {site_url(request)}/.well-known/security.txt",
        "",
    ])
    return HttpResponse(body, content_type="text/plain; charset=utf-8")
