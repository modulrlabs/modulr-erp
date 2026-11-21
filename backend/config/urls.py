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
from django.urls import path, include
from django.http import JsonResponse


def api_root_view(request):
    """
    Root endpoint view providing API health status and available routes.
    """
    return JsonResponse({
        "status": "healthy",
        "project": "Businezz ERP + POS Multi-Tenant SaaS",
        "version": "1.0.0",
        "endpoints": {
            "admin_panel": "/admin/",
            "auth": {
                "register": "/api/auth/register/",
                "login": "/api/auth/login/",
                "token_refresh": "/api/auth/token/refresh/",
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
    path('api/auth/', include('core.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/sales/', include('sales.urls')),
]
