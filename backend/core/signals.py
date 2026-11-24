from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from .audit import get_client_ip, log_audit_event
from .models import User


@receiver(user_login_failed)
def audit_user_login_failed(sender, credentials, request=None, **kwargs):
    """
    Signal receiver capturing failed authentication attempts.

    WHY:
    Detects brute-force password guessing, credential stuffing, and compromised accounts.
    Captures attempted username, IP address, and User-Agent without leaking passwords.
    """
    attempted_username = credentials.get('username') if credentials else None
    user = User.objects.filter(username=attempted_username).first() if attempted_username else None
    shop = getattr(user, 'shop', None) if user else None

    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:255] if request else ''

    log_audit_event(
        action='LOGIN_FAILED',
        target_model='User',
        target_id=str(getattr(user, 'public_id', user.pk)) if user else '',
        shop=shop,
        actor=None,
        actor_username=attempted_username or '',
        before_state={'attempted_username': attempted_username},
        after_state={'status': 'FAILED'},
        ip_address=ip_address,
        user_agent=user_agent,
    )
