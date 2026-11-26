"""Registration, session login/logout and the password reset flow."""

import pytest
from django.core import mail
from django.urls import reverse

from apps.companies.models import Company
from apps.users.models import User

pytestmark = pytest.mark.django_db


REGISTER_URL = reverse('auth-register')
LOGIN_URL = reverse('auth-login')
LOGOUT_URL = reverse('auth-logout')
ME_URL = reverse('auth-me')
RESET_URL = reverse('auth-password-reset')
RESET_CONFIRM_URL = reverse('auth-password-reset-confirm')
CHANGE_URL = reverse('auth-password-change')


def register_payload(**overrides):
    payload = {
        'username': 'new_clerk',
        'email': 'new_clerk@acme.example',
        'password': 'a-very-strong-pass-42',
        'company_name': 'Fresh Company',
    }
    payload.update(overrides)
    return payload


class TestRegistration:
    def test_creates_employee_and_company(self, api_client):
        response = api_client.post(REGISTER_URL, register_payload())

        assert response.status_code == 201
        assert response.data['username'] == 'new_clerk'
        assert response.data['company']['name'] == 'Fresh Company'

        user = User.objects.get(username='new_clerk')
        assert user.check_password('a-very-strong-pass-42')
        assert user.company.name == 'Fresh Company'

    def test_joins_an_existing_company(self, api_client, company):
        response = api_client.post(
            REGISTER_URL, register_payload(company_name=company.name)
        )

        assert response.status_code == 201
        assert response.data['company']['id'] == company.pk
        assert Company.objects.count() == 1

    def test_rejects_duplicate_email(self, api_client, employee):
        response = api_client.post(REGISTER_URL, register_payload(email=employee.email))

        assert response.status_code == 400
        assert 'email' in response.data

    def test_rejects_duplicate_username(self, api_client, employee):
        response = api_client.post(
            REGISTER_URL, register_payload(username=employee.username)
        )

        assert response.status_code == 400
        assert 'username' in response.data

    def test_rejects_weak_password(self, api_client):
        response = api_client.post(REGISTER_URL, register_payload(password='123'))

        assert response.status_code == 400
        assert 'password' in response.data

    def test_password_is_never_echoed(self, api_client):
        response = api_client.post(REGISTER_URL, register_payload())

        assert 'password' not in response.data


class TestLogin:
    def test_login_sets_the_session_cookie(self, api_client, employee):
        response = api_client.post(
            LOGIN_URL, {'login': employee.username, 'password': 'sup3r-secret-pass'}
        )

        assert response.status_code == 200
        assert 'inventory_sessionid' in response.cookies
        assert response.data['user']['username'] == employee.username

    def test_login_with_email(self, api_client, employee):
        response = api_client.post(
            LOGIN_URL, {'login': employee.email, 'password': 'sup3r-secret-pass'}
        )

        assert response.status_code == 200

    def test_wrong_password_is_rejected(self, api_client, employee):
        response = api_client.post(
            LOGIN_URL, {'login': employee.username, 'password': 'nope'}
        )

        # DRF reports 403 rather than 401 for session auth, because session
        # authentication offers no ``WWW-Authenticate`` challenge.
        assert response.status_code == 403

    def test_session_grants_access_to_the_api(self, api_client, employee):
        api_client.post(
            LOGIN_URL, {'login': employee.username, 'password': 'sup3r-secret-pass'}
        )

        response = api_client.get(ME_URL)

        assert response.status_code == 200
        assert response.data['email'] == employee.email

    def test_logout_ends_the_session(self, api_client, employee):
        api_client.post(
            LOGIN_URL, {'login': employee.username, 'password': 'sup3r-secret-pass'}
        )

        assert api_client.post(LOGOUT_URL).status_code == 200
        assert api_client.get(ME_URL).status_code in (401, 403)

    def test_api_requires_authentication(self, api_client):
        response = api_client.get(reverse('product-list'))

        assert response.status_code in (401, 403)

    def test_employee_without_company_is_refused(self, api_client, db):
        orphan = User.objects.create_user(
            username='orphan', email='orphan@example.com', password='sup3r-secret-pass'
        )
        api_client.force_authenticate(user=orphan)

        assert api_client.get(reverse('product-list')).status_code == 403


class TestPasswordReset:
    def test_sends_an_email_with_a_working_link(self, api_client, employee):
        response = api_client.post(RESET_URL, {'email': employee.email})

        assert response.status_code == 200
        assert len(mail.outbox) == 1

        uid, token = self._extract_credentials(mail.outbox[0].body)
        confirm = api_client.post(
            RESET_CONFIRM_URL,
            {'uid': uid, 'token': token, 'new_password': 'brand-new-pass-77'},
        )

        assert confirm.status_code == 200
        employee.refresh_from_db()
        assert employee.check_password('brand-new-pass-77')

    def test_unknown_address_does_not_leak(self, api_client):
        response = api_client.post(RESET_URL, {'email': 'nobody@example.com'})

        assert response.status_code == 200
        assert mail.outbox == []

    def test_token_cannot_be_reused(self, api_client, employee):
        api_client.post(RESET_URL, {'email': employee.email})
        uid, token = self._extract_credentials(mail.outbox[0].body)
        body = {'uid': uid, 'token': token, 'new_password': 'brand-new-pass-77'}

        assert api_client.post(RESET_CONFIRM_URL, body).status_code == 200
        assert api_client.post(RESET_CONFIRM_URL, body).status_code == 400

    def test_invalid_token_is_rejected(self, api_client, employee):
        api_client.post(RESET_URL, {'email': employee.email})
        uid, _ = self._extract_credentials(mail.outbox[0].body)

        response = api_client.post(
            RESET_CONFIRM_URL,
            {'uid': uid, 'token': 'not-a-token', 'new_password': 'brand-new-pass-77'},
        )

        assert response.status_code == 400
        assert 'token' in response.data

    @staticmethod
    def _extract_credentials(body: str) -> tuple[str, str]:
        link = next(line for line in body.splitlines() if 'uid=' in line)
        query = link.split('?', 1)[1]
        params = dict(pair.split('=', 1) for pair in query.split('&'))
        return params['uid'], params['token']


class TestPasswordChange:
    def test_employee_can_change_own_password(self, client, employee):
        response = client.post(
            CHANGE_URL,
            {'current_password': 'sup3r-secret-pass', 'new_password': 'another-good-pass-9'},
        )

        assert response.status_code == 200
        employee.refresh_from_db()
        assert employee.check_password('another-good-pass-9')

    def test_wrong_current_password_is_rejected(self, client):
        response = client.post(
            CHANGE_URL,
            {'current_password': 'wrong', 'new_password': 'another-good-pass-9'},
        )

        assert response.status_code == 400
        assert 'current_password' in response.data
