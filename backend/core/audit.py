import contextvars
import datetime
import uuid
from decimal import Decimal

_audit_request_context = contextvars.ContextVar('audit_request_context', default=None)

SENSITIVE_KEYWORDS = ('password', 'token', 'refresh', 'access', 'secret')


def get_client_ip(request):
    """
    Safely extract client IP address from request META.
    """
    if not request:
        return None
    return request.META.get('REMOTE_ADDR')


def get_current_request_context():
    """
    Retrieve current request context from contextvars.
    """
    ctx = _audit_request_context.get()
    if not ctx:
        return {}
    req = ctx.get('request')
    user = getattr(req, 'user', None) if req else None
    return {
        'request': req,
        'user': user,
        'ip_address': ctx.get('ip_address'),
        'user_agent': ctx.get('user_agent', ''),
    }


class AuditRequestContextMiddleware:
    """
    Middleware that captures request metadata (client IP, user agent, user) into
    thread-safe Python contextvars. This enables both synchronous view operations
    and asynchronous / signal handlers to reliably attribute audit logs to actors.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
        context_data = {
            'request': request,
            'ip_address': ip_address,
            'user_agent': user_agent,
        }
        token = _audit_request_context.set(context_data)
        try:
            response = self.get_response(request)
        finally:
            _audit_request_context.reset(token)
        return response


def _sanitize_value(val):
    if isinstance(val, dict):
        return sanitize_audit_state(val)
    elif isinstance(val, (list, tuple)):
        return [_sanitize_value(item) for item in val]
    elif isinstance(val, set):
        return [_sanitize_value(item) for item in sorted(list(val), key=str)]
    elif isinstance(val, Decimal):
        return str(val)
    elif isinstance(val, uuid.UUID):
        return str(val)
    elif isinstance(val, (datetime.date, datetime.datetime, datetime.time)):
        return val.isoformat()
    elif isinstance(val, (str, int, float, bool)) or val is None:
        return val
    else:
        return str(val)


def sanitize_audit_state(state):
    """
    Recursively sanitize dictionaries to redact sensitive fields (passwords, tokens)
    and serialize Decimals, UUIDs, and datetimes into JSON-safe representations.
    """
    if not isinstance(state, dict):
        return {}
    clean = {}
    for k, v in state.items():
        key_lower = str(k).lower()
        if any(sensitive in key_lower for sensitive in SENSITIVE_KEYWORDS):
            clean[k] = "[REDACTED]"
        else:
            clean[k] = _sanitize_value(v)
    return clean


def log_audit_event(
    action,
    target_model,
    target_id="",
    before_state=None,
    after_state=None,
    shop=None,
    actor=None,
    actor_username=None,
    ip_address=None,
    user_agent=None,
):
    """
    Centralized service helper to record an immutable AuditLog entry.

    WHY:
    Guarantees consistent data sanitization (stripping passwords & tokens),
    converts non-JSON primitives into serializable forms, and automatically
    resolves actor/IP/shop from the ambient request context when not explicitly passed.
    """
    from .models import AuditLog

    ctx = get_current_request_context()

    # Resolve actor
    if actor is None:
        ctx_user = ctx.get('user')
        if ctx_user and getattr(ctx_user, 'is_authenticated', False):
            actor = ctx_user

    # Resolve actor_username
    if not actor_username:
        if actor and getattr(actor, 'username', None):
            actor_username = actor.username
        else:
            ctx_user = ctx.get('user')
            if ctx_user and getattr(ctx_user, 'username', None):
                actor_username = ctx_user.username
            else:
                actor_username = ""

    # Resolve shop
    if shop is None:
        if actor and getattr(actor, 'shop', None):
            shop = actor.shop

    # Resolve IP and User Agent
    if ip_address is None:
        ip_address = ctx.get('ip_address')
    if user_agent is None:
        user_agent = ctx.get('user_agent', '')

    # Sanitize before/after states
    clean_before = sanitize_audit_state(before_state or {})
    clean_after = sanitize_audit_state(after_state or {})

    # Ensure target_id is a string (e.g. public_id)
    target_id_str = str(target_id) if target_id is not None else ""

    return AuditLog.objects.create(
        shop=shop,
        actor=actor,
        actor_username=actor_username or "",
        action=action,
        target_model=target_model,
        target_id=target_id_str,
        before_state=clean_before,
        after_state=clean_after,
        ip_address=ip_address,
        user_agent=user_agent or "",
    )
