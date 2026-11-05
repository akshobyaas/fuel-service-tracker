"""
Automated tests for PitLog's core logic: auth/OTP, cross-user data isolation,
and the odometer-ordering validator. Not exhaustive — these cover the parts
that are easy to silently break and hard to notice by clicking around
manually (an inactive-but-not-quite user, a chronological-not-insertion-order
odometer check, one user reaching another user's vehicle by guessing an id).

Run with: python manage.py test
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import FuelEntry, Vehicle
from .views import _validate_odometer_order


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegistrationOTPTests(TestCase):
    """Registration must stay blocked until the emailed code is verified."""

    def setUp(self):
        self.data = {
            'username': 'newuser', 'email': 'newuser@example.com',
            'password1': 'Sup3rSecret!42', 'password2': 'Sup3rSecret!42',
        }

    def test_register_creates_inactive_user_and_sends_one_email(self):
        self.client.post(reverse('register'), self.data)
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('newuser@example.com', mail.outbox[0].to)

    def test_cannot_log_in_with_password_before_verifying(self):
        self.client.post(reverse('register'), self.data)
        response = self.client.post(reverse('login'), {
            'username': 'newuser', 'password': 'Sup3rSecret!42',
        })
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(response.status_code, 200)  # re-rendered with an error, not logged in

    def test_wrong_code_is_rejected_then_correct_code_activates_account(self):
        self.client.post(reverse('register'), self.data)
        user = User.objects.get(username='newuser')

        bad = self.client.post(reverse('verify_otp'), {'code': '000000'})
        self.assertContains(bad, 'Incorrect code')
        user.refresh_from_db()
        self.assertFalse(user.is_active)

        code = self._extract_code(mail.outbox[-1].body)
        good = self.client.post(reverse('verify_otp'), {'code': code}, follow=True)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.email_verified)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(good.status_code, 200)

    def test_abandoned_registration_can_be_retried_without_duplicate_user(self):
        self.client.post(reverse('register'), self.data)  # never verified
        self.client.post(reverse('register'), self.data)  # retry, same client
        self.assertEqual(User.objects.filter(username='newuser').count(), 1)

    @staticmethod
    def _extract_code(body):
        import re
        return re.search(r'\b(\d{6})\b', body).group(1)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class LoginTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # login-throttle counters are process-cache-backed, not DB-backed
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='Sup3rSecret!42',
            is_active=True,
        )

    def test_password_login_by_username(self):
        r = self.client.post(reverse('login'), {'username': 'alice', 'password': 'Sup3rSecret!42'})
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(r.status_code, 302)

    def test_password_login_by_email(self):
        r = self.client.post(reverse('login'), {'username': 'alice@example.com', 'password': 'Sup3rSecret!42'})
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(r.status_code, 302)

    def test_wrong_password_does_not_log_in(self):
        self.client.post(reverse('login'), {'username': 'alice', 'password': 'WrongPassword'})
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_repeated_failed_logins_get_throttled(self):
        for _ in range(5):
            self.client.post(reverse('login'), {'username': 'alice', 'password': 'WrongPassword'})
        # 6th attempt, even with the CORRECT password, should now be blocked
        r = self.client.post(reverse('login'), {'username': 'alice', 'password': 'Sup3rSecret!42'})
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(r, 'Too many failed sign-in attempts')

    def test_otp_login_works_and_lets_password_be_reset_without_old_one(self):
        r = self.client.post(reverse('login'), {'mode': 'otp_request', 'identifier': 'alice'})
        self.assertRedirects(r, reverse('verify_otp'))
        code = RegistrationOTPTests._extract_code(mail.outbox[-1].body)
        self.client.post(reverse('verify_otp'), {'code': code})
        self.assertIn('_auth_user_id', self.client.session)

        # Logged in via OTP: change-password page should NOT ask for the old
        # password, and should accept a new one directly.
        r = self.client.get(reverse('profile_password'))
        self.assertNotContains(r, 'Current password')
        r = self.client.post(reverse('profile_password'), {
            'new_password1': 'BrandNewPass!7', 'new_password2': 'BrandNewPass!7',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass!7'))

    def test_normal_password_change_still_requires_old_password(self):
        self.client.login(username='alice', password='Sup3rSecret!42')
        r = self.client.post(reverse('profile_password'), {
            'old_password': 'WrongOldPassword',
            'new_password1': 'BrandNewPass!7', 'new_password2': 'BrandNewPass!7',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('BrandNewPass!7'))
        self.assertContains(r, 'correct')  # Django's own "old password incorrect" copy


class VehicleOwnershipTests(TestCase):
    """One user must never be able to view, edit or delete another user's data."""

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pw12345678', is_active=True)
        self.bob = User.objects.create_user(username='bob', password='pw12345678', is_active=True)
        self.alices_bike = Vehicle.objects.create(
            user=self.alice, brand='Honda', name='Activa', year=2022, fuel_type='Petrol'
        )
        self.client.login(username='bob', password='pw12345678')

    def test_cannot_view_another_users_vehicle_edit_page(self):
        r = self.client.get(reverse('edit_vehicle', args=[self.alices_bike.id]))
        self.assertEqual(r.status_code, 404)

    def test_cannot_delete_another_users_vehicle(self):
        r = self.client.post(reverse('delete_vehicle', args=[self.alices_bike.id]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Vehicle.objects.filter(id=self.alices_bike.id).exists())

    def test_bad_non_numeric_id_is_404_not_500(self):
        # get_object_or_404 alone only catches DoesNotExist — a non-numeric id
        # would otherwise hit the ORM as an uncaught ValueError.
        r = self.client.get('/edit-vehicle/not-a-number/')
        self.assertEqual(r.status_code, 404)


class OdometerOrderingTests(TestCase):
    """Odometer readings must be non-decreasing by DATE, not by insertion order."""

    def setUp(self):
        self.user = User.objects.create_user(username='rider', password='pw12345678')
        self.vehicle = Vehicle.objects.create(
            user=self.user, brand='Bajaj', name='Pulsar', year=2021, fuel_type='Petrol'
        )

    def test_backfilling_an_older_entry_after_a_newer_one_is_allowed(self):
        # Insert the NEWER entry first (as happens if someone starts logging
        # today, then goes back and backfills last month's fill-up).
        FuelEntry.objects.create(
            vehicle=self.vehicle, litres=10, cost=1000,
            odometer=5000, date=date.today(), full_tank=True,
        )
        qs = FuelEntry.objects.filter(vehicle=self.vehicle)
        error = _validate_odometer_order(
            qs, 'date', 'odometer',
            new_date=date.today() - timedelta(days=30), new_odo=4500,
        )
        self.assertIsNone(error, 'Backfilling an earlier, lower reading must be allowed')

    def test_lower_odometer_than_an_earlier_entry_is_rejected(self):
        FuelEntry.objects.create(
            vehicle=self.vehicle, litres=10, cost=1000,
            odometer=5000, date=date.today() - timedelta(days=30), full_tank=True,
        )
        qs = FuelEntry.objects.filter(vehicle=self.vehicle)
        error = _validate_odometer_order(
            qs, 'date', 'odometer',
            new_date=date.today(), new_odo=4000,  # lower reading, but LATER date
        )
        self.assertIsNotNone(error)

    def test_higher_odometer_than_a_later_entry_is_rejected(self):
        FuelEntry.objects.create(
            vehicle=self.vehicle, litres=10, cost=1000,
            odometer=5000, date=date.today(), full_tank=True,
        )
        qs = FuelEntry.objects.filter(vehicle=self.vehicle)
        error = _validate_odometer_order(
            qs, 'date', 'odometer',
            new_date=date.today() - timedelta(days=30), new_odo=6000,  # higher, but EARLIER date
        )
        self.assertIsNotNone(error)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AuthSecurityTests(TestCase):
    """Regression tests for login redirect, pending-signup reclaim and the
    throttle's client-IP detection."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='Sup3rSecret!42',
            is_active=True,
        )

    def _login(self, next_url):
        return self.client.post(
            reverse('login') + '?next=' + next_url,
            {'username': 'alice', 'password': 'Sup3rSecret!42'},
        )

    def test_login_ignores_offsite_next(self):
        r = self._login('https://evil.example/phish')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse('home'))

    def test_login_ignores_protocol_relative_next(self):
        r = self._login('//evil.example/phish')
        self.assertEqual(r.url, reverse('home'))

    def test_login_honours_same_site_next(self):
        r = self._login(reverse('vehicles'))
        self.assertEqual(r.url, reverse('vehicles'))

    def test_stranger_cannot_wipe_someone_elses_pending_signup(self):
        data = {'username': 'bob', 'email': 'bob@example.com',
                'password1': 'Sup3rSecret!42', 'password2': 'Sup3rSecret!42'}
        self.client.post(reverse('register'), data)          # Bob, mid sign-up
        pending = User.objects.get(username='bob')
        from django.test import Client
        Client().post(reverse('register'), {**data, 'email': 'attacker@example.com'})
        self.assertTrue(User.objects.filter(id=pending.id).exists())

    def test_abandoned_pending_signup_can_be_reclaimed_after_expiry(self):
        from django.utils import timezone
        data = {'username': 'bob', 'email': 'bob@example.com',
                'password1': 'Sup3rSecret!42', 'password2': 'Sup3rSecret!42'}
        self.client.post(reverse('register'), data)
        User.objects.filter(username='bob').update(
            date_joined=timezone.now() - timedelta(hours=1))
        from django.test import Client
        Client().post(reverse('register'), data)              # someone else, later
        self.assertEqual(User.objects.filter(username='bob').count(), 1)
        self.assertGreater(User.objects.get(username='bob').date_joined,
                           timezone.now() - timedelta(minutes=5))

    def test_spoofed_forwarded_for_does_not_bypass_throttle(self):
        for i in range(5):
            self.client.post(reverse('login'), {'username': 'alice', 'password': 'nope'},
                             HTTP_X_FORWARDED_FOR=f'10.0.0.{i}, 203.0.113.7')
        r = self.client.post(reverse('login'), {'username': 'alice', 'password': 'Sup3rSecret!42'},
                             HTTP_X_FORWARDED_FOR='10.9.9.9, 203.0.113.7')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(r, 'Too many failed sign-in attempts')
