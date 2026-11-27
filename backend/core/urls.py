from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AuditLogViewSet,
    ChangePasswordView,
    CookieTokenRefreshView,
    CurrentUserView,
    CustomTokenObtainPairView,
    LogoutView,
    RegisterView,
)

router = DefaultRouter()
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', CustomTokenObtainPairView.as_view(), name='auth_login'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('me/', CurrentUserView.as_view(), name='auth_me'),
    path('change-password/', ChangePasswordView.as_view(), name='auth_change_password'),
]
