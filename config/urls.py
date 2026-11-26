"""Root URL configuration.

Every app exposes a DRF router under ``apps.<app>.urls`` and they are all
mounted below ``/api/``. The OpenAPI schema and its two viewers sit next to
them.
"""

from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

api_patterns = [
    path('', include('apps.users.urls')),
    path('', include('apps.companies.urls')),
    path('', include('apps.warehouses.urls')),
    path('', include('apps.products.urls')),
    path('', include('apps.transactions.urls')),
    path('', include('apps.reports.urls')),
]

docs_patterns = [
    # Raw OpenAPI 3 document (?format=json for JSON instead of YAML).
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    # ``ensure_csrf_cookie`` so the page itself hands out the csrftoken that
    # the Swagger UI request interceptor needs for unsafe "Try it out" calls.
    path(
        'docs/',
        ensure_csrf_cookie(SpectacularSwaggerView.as_view(url_name='schema')),
        name='swagger-ui',
    ),
    path(
        'redoc/',
        SpectacularRedocView.as_view(url_name='schema'),
        name='redoc',
    ),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(api_patterns)),
    path('api/', include(docs_patterns)),
    path('api/auth/browsable/', include('rest_framework.urls')),
]
