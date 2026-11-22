"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def api_root_view(request):
    """
    Root endpoint view providing API health status and available routes.
    """
    return JsonResponse({
        "status": "healthy",
        "project": "Businezz ERP + POS Multi-Tenant SaaS",
        "version": "1.0.0",
        "documentation": {
            "swagger_ui": "/api/docs/",
            "redoc": "/api/redoc/",
            "openapi_schema": "/api/schema/",
        },
        "endpoints": {
            "admin_panel": "/admin/",
            "auth": {
                "register": "/api/auth/register/",
                "login": "/api/auth/login/",
                "refresh": "/api/auth/token/refresh/",
                "me": "/api/auth/me/",
            },
            "inventory": {
                "categories": "/api/inventory/categories/",
                "products": "/api/inventory/products/",
                "by_barcode": "/api/inventory/products/by-barcode/?code=<barcode>",
                "upload_csv": "/api/inventory/products/upload-csv/",
            },
            "sales": {
                "invoices": "/api/sales/invoices/",
                "dashboard": "/api/sales/dashboard/",
                "customers": "/api/sales/customers/",
                "credit_payments": "/api/sales/credit-payments/",
                "pd_cheques": "/api/sales/pd-cheques/",
                "upcoming_cheques": "/api/sales/pd-cheques/upcoming/",
            }
        }
    })


urlpatterns = [
    path('', api_root_view, name='api_root'),
    path('admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/auth/', include('core.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/sales/', include('sales.urls')),
]
