from axes.models import AccessAttempt
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Shop, User


class AuthSecurityAndCookieTests(APITestCase):
    """
    Test suite for Phase 1A Task 1:
    - httpOnly Cookie Auth
    - CSRF Hardening (X-Requested-With & Origin verification)
    - Token Rotation and Blacklisting
    - Brute Force & Rate Limit Throttling
    """

    def setUp(self):
        cache.clear()
        AccessAttempt.objects.all().delete()
        self.shop = Shop.objects.create(name="Modulr Test Shop", is_active=True)
        self.user = User.objects.create_user(
            username="owner_test",
            password="SecurePassword123!",
            shop=self.shop,
            role=User.Role.OWNER,
            is_active=True,
        )
        self.login_payload = {
            "username": "owner_test",
            "password": "SecurePassword123!",
        }
        self.csrf_headers = {
            "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
            "HTTP_ORIGIN": "http://localhost:5173",
        }

    @override_settings(AUTH_REFRESH_IN_BODY=False)
    def test_default_auth_refresh_in_body_false_omits_refresh_from_payload(self):
        """
        When AUTH_REFRESH_IN_BODY=False:
        1. Login sets httpOnly cookie and omits 'refresh' from JSON response body.
        2. Register sets httpOnly cookie and omits 'refresh' from JSON tokens object.
        """
        # 1. Test Login
        response = self.client.post('/api/auth/login/', data=self.login_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Cookie must be set, httpOnly, and have matching path
        self.assertIn(settings.AUTH_REFRESH_COOKIE_NAME, response.cookies)
        cookie = response.cookies[settings.AUTH_REFRESH_COOKIE_NAME]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['path'], settings.AUTH_REFRESH_COOKIE_PATH)

        # Refresh must NOT be in JSON body
        self.assertNotIn('refresh', response.data)
        self.assertIn('access', response.data)

        # 2. Test Register
        register_payload = {
            "shop_name": "New Mart",
            "username": "new_owner",
            "password": "SecurePassword123!",
        }
        reg_response = self.client.post('/api/auth/register/', data=register_payload, format='json')
        self.assertEqual(reg_response.status_code, status.HTTP_201_CREATED)
        self.assertIn(settings.AUTH_REFRESH_COOKIE_NAME, reg_response.cookies)
        self.assertNotIn('refresh', reg_response.data['tokens'])
        self.assertIn('access', reg_response.data['tokens'])

    @override_settings(AUTH_REFRESH_IN_BODY=True)
    def test_auth_refresh_in_body_true_includes_refresh_in_payload_and_cookie(self):
        """
        When AUTH_REFRESH_IN_BODY=True:
        Both the httpOnly cookie AND the JSON response body include the refresh token.
        """
        # 1. Test Login
        response = self.client.post('/api/auth/login/', data=self.login_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(settings.AUTH_REFRESH_COOKIE_NAME, response.cookies)
        self.assertIn('refresh', response.data)
        self.assertIn('access', response.data)

        # 2. Test Register
        register_payload = {
            "shop_name": "Body Test Mart",
            "username": "body_owner",
            "password": "SecurePassword123!",
        }
        reg_response = self.client.post('/api/auth/register/', data=register_payload, format='json')
        self.assertEqual(reg_response.status_code, status.HTTP_201_CREATED)
        self.assertIn(settings.AUTH_REFRESH_COOKIE_NAME, reg_response.cookies)
        self.assertIn('refresh', reg_response.data['tokens'])

    def test_csrf_and_origin_enforcement_on_refresh_and_logout(self):
        """
        Refresh and logout endpoints must return 403 Forbidden when:
        1. X-Requested-With header is missing.
        2. Origin or Referer header belongs to an untrusted domain.
        """
        # Authenticate and obtain cookie
        login_res = self.client.post('/api/auth/login/', data=self.login_payload, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        # A. Missing X-Requested-With header
        res_no_header = self.client.post('/api/auth/token/refresh/')
        self.assertEqual(res_no_header.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Missing or invalid X-Requested-With", str(res_no_header.data))

        logout_no_header = self.client.post('/api/auth/logout/')
        self.assertEqual(logout_no_header.status_code, status.HTTP_403_FORBIDDEN)

        # B. Untrusted Origin
        evil_origin_headers = {
            "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
            "HTTP_ORIGIN": "https://attacker-domain.evil.com",
        }
        res_evil = self.client.post('/api/auth/token/refresh/', **evil_origin_headers)
        self.assertEqual(res_evil.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Untrusted origin/referer", str(res_evil.data))

        logout_evil = self.client.post('/api/auth/logout/', **evil_origin_headers)
        self.assertEqual(logout_evil.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(AUTH_REFRESH_IN_BODY=True)
    def test_valid_refresh_rotates_cookie_and_blacklists_old_token(self):
        """
        Calling /api/auth/token/refresh/ rotates the refresh token.
        Replaying the old refresh token must fail with 401 Unauthorized.
        """
        login_res = self.client.post('/api/auth/login/', data=self.login_payload, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        old_refresh_token = login_res.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value

        # First refresh: Should succeed and rotate tokens
        refresh_res = self.client.post('/api/auth/token/refresh/', **self.csrf_headers)
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_res.data)

        new_refresh_token = refresh_res.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
        self.assertNotEqual(old_refresh_token, new_refresh_token)

        # Replay Attack: Try to use old_refresh_token
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = old_refresh_token
        replay_res = self.client.post('/api/auth/token/refresh/', **self.csrf_headers)
        self.assertEqual(replay_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_token_and_clears_cookie(self):
        """
        Logout blacklists the current refresh token and instructs the browser to delete the cookie.
        """
        login_res = self.client.post('/api/auth/login/', data=self.login_payload, format='json')
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        active_token = login_res.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value

        # Logout
        logout_res = self.client.post('/api/auth/logout/', **self.csrf_headers)
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        # Cookie should be cleared (max-age=0 or empty)
        logout_cookie = logout_res.cookies[settings.AUTH_REFRESH_COOKIE_NAME]
        self.assertIn(logout_cookie['max-age'], [0, '0', ''])

        # Attempting to refresh with the blacklisted token must be rejected (401)
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = active_token
        refresh_res = self.client.post('/api/auth/token/refresh/', **self.csrf_headers)
        self.assertEqual(refresh_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_throttling_returns_429(self):
        """
        Rate limiting on login endpoint:
        Allowed rate is 5/min. The 6th request within a minute must return 429 Too Many Requests.
        """
        payload = {"username": "throttle_user", "password": "WrongPassword!"}

        for _i in range(5):
            res = self.client.post('/api/auth/login/', data=payload, format='json')
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # 6th attempt triggers 429
        throttled_res = self.client.post('/api/auth/login/', data=payload, format='json')
        self.assertEqual(throttled_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
