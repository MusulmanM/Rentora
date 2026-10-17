from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.conf import settings
from django.conf.urls.static import static
from django.templatetags.static import static as static_url
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve

from core import seo

urlpatterns = [
    # Browsers and search engines ask for /favicon.ico regardless of the <link> tags.
    path("favicon.ico", RedirectView.as_view(url=static_url("core/favicon.ico"), permanent=True)),
    path("robots.txt", seo.robots_txt, name="robots-txt"),
    path("sitemap.xml", sitemap, {"sitemaps": seo.SITEMAPS}, name="django.contrib.sitemaps.views.sitemap"),
    path(".well-known/security.txt", seo.security_txt, name="security-txt"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    # static() is a no-op when DEBUG is off, so register the media view explicitly.
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
