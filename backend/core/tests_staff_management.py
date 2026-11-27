import json
import threading

from django.db import connections
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AuditLog, Shop, User


class StaffManagementTests(APITestCase):
    """
    Comprehensive tests for Step 4a-3: /api/staff/ CRUD, username/password generation,
    anti-privilege-escalation, last-owner protection, token blacklisting, password hygiene,
    and cross-tenant isolation.
    """

    def setUp(self):
        self.shop_a = Shop.objects.create(name="Staff Mart A", is_active=True)
        self.owner_a = User.objects.create_user(
            username="staff_owner_a",
            password="Password123!",
            shop=self.shop_a,
            role=User.Role.OWNER,
        )
        self.manager_a = User.objects.create_user(
            username="staff_mgr_a",
            password="Password123!",
            shop=self.shop_a,
            role=User.Role.MANAGER,
        )
        self.cashier_a = User.objects.create_user(
            username="staff_cashier_a",
            password="Password123!",
            shop=self.shop_a,
            role=User.Role.CASHIER,
        )
        self.accountant_a = User.objects.create_user(
            username="staff_acc_a",
            password="Password123!",
            shop=self.shop_a,
            role=User.Role.ACCOUNTANT,
        )

        self.shop_b = Shop.objects.create(name="Staff Mart B", is_active=True)
        self.owner_b = User.objects.create_user(
            username="staff_owner_b",
            password="Password123!",
            shop=self.shop_b,
            role=User.Role.OWNER,
        )
        self.cashier_b = User.objects.create_user(
            username="staff_cashier_b",
            password="Password123!",
            shop=self.shop_b,
            role=User.Role.CASHIER,
        )

    def test_staff_creation_temp_password_sinhala_fallback_and_username_immutability(self):
        """
        Creating staff generates username + temp password once; non-ASCII first_name falls back
        to 'staff.<4chars>'; PATCH cannot alter username.
        """
        self.client.force_authenticate(user=self.owner_a)

        # 1. ASCII first_name
        res_ascii = self.client.post(
            '/api/staff/',
            data={'first_name': 'Nimal', 'last_name': 'Perera', 'role': 'CASHIER'},
            format='json',
        )
        self.assertEqual(res_ascii.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_ascii.data['username'].startswith('nimal.'))
        self.assertEqual(len(res_ascii.data['username']), len('nimal.') + 4)
        self.assertIn('temporary_password', res_ascii.data)
        self.assertTrue(res_ascii.data['must_change_password'])

        # 2. Sinhala first_name fallback
        res_si = self.client.post(
            '/api/staff/',
            data={'first_name': 'නිමල්', 'role': 'CASHIER'},
            format='json',
        )
        self.assertEqual(res_si.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_si.data['username'].startswith('staff.'))
        self.assertEqual(len(res_si.data['username']), len('staff.') + 4)

        # 3. Username is immutable on PATCH
        original_username = res_ascii.data['username']
        patch_res = self.client.patch(
            f"/api/staff/{res_ascii.data['public_id']}/",
            data={'username': 'hacked.name', 'first_name': 'Nimal Updated'},
            format='json',
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['username'], original_username)
        self.assertEqual(patch_res.data['first_name'], 'Nimal Updated')

    def test_privilege_escalation_blocks_manager_and_cashier_and_owner_self_demote(self):
        """
        Toggled MANAGER can manage CASHIER only (403 on OWNER/MANAGER/INVENTORY_MANAGER/ACCOUNTANT);
        CASHIER gets 403 on /api/staff/; OWNER cannot change own role.
        """
        # Cashier blocked
        self.client.force_authenticate(user=self.cashier_a)
        self.assertEqual(self.client.get('/api/staff/').status_code, status.HTTP_403_FORBIDDEN)

        # Manager without toggle blocked
        self.client.force_authenticate(user=self.manager_a)
        self.assertEqual(self.client.get('/api/staff/').status_code, status.HTTP_403_FORBIDDEN)

        # Enable managers_can_manage_cashiers toggle
        self.shop_a.settings.managers_can_manage_cashiers = True
        self.shop_a.settings.save()

        # Manager can list (sees only cashiers) and create CASHIER
        list_res = self.client.get('/api/staff/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertTrue(all(u['role'] == 'CASHIER' for u in list_res.data))

        create_cashier = self.client.post(
            '/api/staff/',
            data={'first_name': 'Kasun', 'role': 'CASHIER'},
            format='json',
        )
        self.assertEqual(create_cashier.status_code, status.HTTP_201_CREATED)

        # Manager gets 403 trying to create non-CASHIER roles
        for role in ('OWNER', 'MANAGER', 'INVENTORY_MANAGER', 'ACCOUNTANT'):
            res = self.client.post(
                '/api/staff/',
                data={'first_name': 'Blocked', 'role': role},
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Manager gets 403 trying to touch OWNER or ACCOUNTANT
        for target in (self.owner_a, self.accountant_a):
            self.assertEqual(
                self.client.patch(
                    f'/api/staff/{target.public_id}/',
                    data={'first_name': 'X'},
                    format='json',
                ).status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self.client.post(f'/api/staff/{target.public_id}/deactivate/').status_code,
                status.HTTP_403_FORBIDDEN,
            )
            self.assertEqual(
                self.client.post(f'/api/staff/{target.public_id}/reset-password/').status_code,
                status.HTTP_403_FORBIDDEN,
            )

        # OWNER cannot change their own role
        self.client.force_authenticate(user=self.owner_a)
        self_role_res = self.client.patch(
            f'/api/staff/{self.owner_a.public_id}/',
            data={'role': 'MANAGER'},
            format='json',
        )
        self.assertEqual(self_role_res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_last_owner_cannot_be_demoted_or_deactivated(self):
        """Last active OWNER of a shop cannot be demoted or deactivated."""
        self.client.force_authenticate(user=self.owner_a)

        # Deactivate last owner -> 400
        deact_res = self.client.post(f'/api/staff/{self.owner_a.public_id}/deactivate/')
        self.assertEqual(deact_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.owner_a.refresh_from_db()
        self.assertTrue(self.owner_a.is_active)

        # Second owner tries to demote owner_a when owner_a is made sole active owner?
        # Here owner_a is already sole active owner; test demoting via another owner is tested below
        # when 2 owners exist (one can be demoted, then the remaining 1 cannot).
        res_o2 = self.client.post(
            '/api/staff/',
            data={'first_name': 'SecondOwner', 'role': 'OWNER'},
            format='json',
        )
        self.assertEqual(res_o2.status_code, status.HTTP_201_CREATED)
        o2_pub_id = res_o2.data['public_id']

        # Demote second owner -> allowed (owner_a still active)
        demote_o2 = self.client.patch(
            f'/api/staff/{o2_pub_id}/',
            data={'role': 'MANAGER'},
            format='json',
        )
        self.assertEqual(demote_o2.status_code, status.HTTP_200_OK)

        # Now owner_a is again the last active owner -> cannot deactivate
        deact_res2 = self.client.post(f'/api/staff/{self.owner_a.public_id}/deactivate/')
        self.assertEqual(deact_res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivation_blocks_access_and_refresh_reactivate_restores_delete_405(self):
        """
        Deactivation immediately blocks existing access & refresh tokens; reactivation restores
        login; DELETE /api/staff/{public_id}/ returns 405 Method Not Allowed.
        """
        refresh = RefreshToken.for_user(self.cashier_a)
        access_token = str(refresh.access_token)

        # Hard delete returns 405
        self.client.force_authenticate(user=self.owner_a)
        del_res = self.client.delete(f'/api/staff/{self.cashier_a.public_id}/')
        self.assertEqual(del_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Deactivate cashier_a
        deact_res = self.client.post(f'/api/staff/{self.cashier_a.public_id}/deactivate/')
        self.assertEqual(deact_res.status_code, status.HTTP_200_OK)
        self.assertFalse(deact_res.data['is_active'])

        # Old access token rejected (401)
        self.client.force_authenticate(user=None)
        res_access = self.client.get(
            '/api/inventory/products/',
            HTTP_AUTHORIZATION=f'Bearer {access_token}',
        )
        self.assertEqual(res_access.status_code, status.HTTP_401_UNAUTHORIZED)

        # Old refresh token blacklisted / rejected (401)
        self.client.cookies['modulr_refresh_token'] = str(refresh)
        res_refresh = self.client.post(
            '/api/auth/token/refresh/',
            {},
            format='json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(res_refresh.status_code, status.HTTP_401_UNAUTHORIZED)

        # Reactivate cashier_a -> login works again
        self.client.force_authenticate(user=self.owner_a)
        react_res = self.client.post(f'/api/staff/{self.cashier_a.public_id}/reactivate/')
        self.assertEqual(react_res.status_code, status.HTTP_200_OK)
        self.assertTrue(react_res.data['is_active'])

        self.client.force_authenticate(user=None)
        login_res = self.client.post(
            '/api/auth/login/',
            data={'username': self.cashier_a.username, 'password': 'Password123!'},
            format='json',
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

    def test_reset_password_blacklists_refresh_sets_flag_and_audit_log_has_no_passwords(self):
        """
        reset-password blacklists refresh tokens, sets must_change_password=True, returns temp
        password once, and NO temporary password appears anywhere in AuditLog.
        """
        self.client.force_authenticate(user=self.owner_a)
        create_res = self.client.post(
            '/api/staff/',
            data={'first_name': 'Saman', 'role': 'CASHIER'},
            format='json',
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        created_temp_pw = create_res.data['temporary_password']
        staff_pub_id = create_res.data['public_id']
        staff_user = User.objects.get(public_id=staff_pub_id)

        # Issue a refresh token for the new staff user
        refresh = RefreshToken.for_user(staff_user)

        # Reset password
        reset_res = self.client.post(f'/api/staff/{staff_pub_id}/reset-password/')
        self.assertEqual(reset_res.status_code, status.HTTP_200_OK)
        reset_temp_pw = reset_res.data['temporary_password']
        self.assertTrue(reset_res.data['must_change_password'])
        self.assertNotEqual(created_temp_pw, reset_temp_pw)

        # Old refresh token must be blacklisted
        self.client.force_authenticate(user=None)
        self.client.cookies['modulr_refresh_token'] = str(refresh)
        res_refresh = self.client.post(
            '/api/auth/token/refresh/',
            {},
            format='json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(res_refresh.status_code, status.HTTP_401_UNAUTHORIZED)

        # Scan all AuditLog rows to ensure neither temp password appears anywhere
        for entry in AuditLog.objects.all():
            serialized_before = json.dumps(entry.before_state)
            serialized_after = json.dumps(entry.after_state)
            combined = (
                f"{entry.action} {entry.target_model} {entry.target_id} "
                f"{entry.actor_username} {serialized_before} {serialized_after}"
            )
            self.assertNotIn(created_temp_pw, combined)
            self.assertNotIn(reset_temp_pw, combined)

    def test_cross_tenant_staff_isolation(self):
        """Owner A cannot list, retrieve, patch, deactivate, or reset Shop B's staff (404)."""
        self.client.force_authenticate(user=self.owner_a)

        list_res = self.client.get('/api/staff/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        usernames = {u['username'] for u in list_res.data}
        self.assertNotIn(self.cashier_b.username, usernames)
        self.assertNotIn(self.owner_b.username, usernames)

        for method, url in (
            ('get', f'/api/staff/{self.cashier_b.public_id}/'),
            ('patch', f'/api/staff/{self.cashier_b.public_id}/'),
            ('post', f'/api/staff/{self.cashier_b.public_id}/deactivate/'),
            ('post', f'/api/staff/{self.cashier_b.public_id}/reset-password/'),
        ):
            res = getattr(self.client, method)(url, data={'first_name': 'Hack'}, format='json')
            self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class LastOwnerConcurrencyTests(TransactionTestCase):
    """
    Concurrency test verifying simultaneous deactivate requests on 2 owners
    never leave a shop with zero active owners.
    """

    def test_concurrent_deactivate_two_owners_leaves_at_least_one_active(self):
        shop = Shop.objects.create(name="Concurrent Shop", is_active=True)
        owner_1 = User.objects.create_user(
            username="conc_owner_1",
            password="Password123!",
            shop=shop,
            role=User.Role.OWNER,
        )
        owner_2 = User.objects.create_user(
            username="conc_owner_2",
            password="Password123!",
            shop=shop,
            role=User.Role.OWNER,
        )

        barrier = threading.Barrier(2)
        results = []

        def deactivate_target(actor, target):
            try:
                client = APIClient()
                client.force_authenticate(user=actor)
                barrier.wait(timeout=5)
                res = client.post(f'/api/staff/{target.public_id}/deactivate/')
                results.append(res.status_code)
            except Exception as exc:  # pragma: no cover - SQLite lock fallback
                results.append(type(exc).__name__)
            finally:
                connections.close_all()

        t1 = threading.Thread(target=deactivate_target, args=(owner_1, owner_2))
        t2 = threading.Thread(target=deactivate_target, args=(owner_2, owner_1))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        active_owner_count = User.objects.filter(
            shop=shop,
            role=User.Role.OWNER,
            is_active=True,
        ).count()
        self.assertGreaterEqual(active_owner_count, 1)
