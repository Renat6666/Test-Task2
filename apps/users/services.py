"""Authentication and account services.

Everything here uses Django's built-in authentication machinery: session login
through ``django.contrib.auth.login`` (cookie based, no JWT) and the standard
``default_token_generator`` for password resets.
"""

import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import AuthenticationFailed

from apps.common.exceptions import BusinessRuleViolation
from apps.companies import services as company_services
from apps.users import selectors

logger = logging.getLogger(__name__)

User = get_user_model()


@transaction.atomic
def register_employee(
    *,
    username: str,
    email: str,
    password: str,
    company_name: str,
    first_name: str = '',
    last_name: str = '',
) -> User:
    """Create an employee and attach them to a company.

    The company is created when the name is new, otherwise the employee joins
    the existing one.
    """
    company = company_services.get_or_create_company(name=company_name)

    user = User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        company=company,
    )
    user.set_password(password)
    user.save()
    return user


def login_employee(*, request, login: str, password: str) -> User:
    """Authenticate and open a session (sets the session cookie).

    ``login`` accepts either the username or the email address.
    """
    user = authenticate(request=request, username=login, password=password)

    if user is None:
        # Allow signing in with an email address as well.
        candidate = selectors.find_by_email(email=login)
        if candidate is not None:
            user = authenticate(
                request=request, username=candidate.get_username(), password=password
            )

    if user is None:
        raise AuthenticationFailed('Invalid credentials.')
    if not user.is_active:
        raise AuthenticationFailed('This account is disabled.')

    django_login(request, user)
    return user


def logout_employee(*, request) -> None:
    """Flush the session and clear the session cookie."""
    django_logout(request)


def request_password_reset(*, email: str) -> None:
    """Email a password reset link.

    Always succeeds from the caller's point of view: revealing whether an
    address is registered would be an account enumeration hole.
    """
    user = selectors.find_by_email(email=email)
    if user is None or not user.is_active:
        logger.info('Password reset requested for unknown address %s', email)
        return

    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = settings.PASSWORD_RESET_URL_TEMPLATE.format(uid=uid, token=token)

    send_mail(
        subject='Inventory: password reset',
        message=(
            f'Hello {user.get_username()},\n\n'
            'Use the link below to choose a new password:\n\n'
            f'{reset_url}\n\n'
            'If you did not ask for a new password you can ignore this email.\n'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def confirm_password_reset(*, uid: str, token: str, new_password: str) -> User:
    """Set a new password from a valid reset token."""
    try:
        user_pk = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_pk)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        raise BusinessRuleViolation({'uid': ['Invalid password reset link.']})

    if not default_token_generator.check_token(user, token):
        raise BusinessRuleViolation({'token': ['This reset link is invalid or expired.']})

    user.set_password(new_password)
    user.save(update_fields=['password'])
    return user


def change_password(*, user: User, current_password: str, new_password: str) -> User:
    """Change the password of a signed-in employee."""
    if not user.check_password(current_password):
        raise BusinessRuleViolation({'current_password': ['Wrong password.']})
    user.set_password(new_password)
    user.save(update_fields=['password'])
    return user
