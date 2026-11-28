"""
Utility helpers for Staff Management:
- ASCII slug + random suffix username generation
- Cryptographically random temporary password generation
- Immediate refresh-token blacklisting for deactivated / reset users
"""

import re
import secrets
import string
import unicodedata

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

_ALNUM_LOWER = string.ascii_lowercase + string.digits
_SYMBOLS = '!@#$%&*'
_RNG = secrets.SystemRandom()


def generate_staff_username(first_name: str, max_attempts: int = 20) -> str:
    """
    Slugify `first_name` to lowercase ASCII alphanumeric characters (falling back to 'staff'
    for non-ASCII/empty input like Sinhala or Tamil), then append '.' + 4 random chars.
    """
    User = get_user_model()
    normalized = (
        unicodedata.normalize('NFKD', first_name or '')
        .encode('ascii', 'ignore')
        .decode('ascii')
    )
    slug = re.sub(r'[^a-z0-9]', '', normalized.lower())[:20] or 'staff'

    for _ in range(max_attempts):
        suffix = ''.join(secrets.choice(_ALNUM_LOWER) for _ in range(4))
        candidate = f'{slug}.{suffix}'
        if not User.objects.filter(username=candidate).exists():
            return candidate

    raise RuntimeError('Failed to generate a unique staff username after maximum attempts.')


def generate_temp_password(length: int = 12) -> str:
    """
    Generate a cryptographically random temporary password satisfying Django's
    AUTH_PASSWORD_VALIDATORS (mixed case, digits, symbols, >= 8 chars).
    """
    effective_len = max(length, 10)
    chars = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(_SYMBOLS),
    ]
    pool = string.ascii_letters + string.digits + _SYMBOLS
    chars.extend(secrets.choice(pool) for _ in range(effective_len - len(chars)))
    _RNG.shuffle(chars)
    return ''.join(chars)


def blacklist_user_refresh_tokens(user) -> int:
    """
    Blacklist all OutstandingToken records belonging to `user` so active refresh tokens
    are immediately invalidated.
    """
    count = 0
    for token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        if created:
            count += 1
    return count
