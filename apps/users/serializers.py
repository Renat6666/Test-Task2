from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.companies.serializers import CompanySerializer

User = get_user_model()


def _validate_password_strength(password: str) -> str:
    """Run Django's configured password validators."""
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    return password


class EmployeeSerializer(serializers.ModelSerializer):
    """Public representation of an employee."""

    company = CompanySerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'company',
            'is_staff',
            'date_joined',
        ]
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[_validate_password_strength])
    company_name = serializers.CharField(max_length=255)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('This username is already taken.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already registered.')
        return value


class LoginSerializer(serializers.Serializer):
    login = serializers.CharField(help_text='Username or email address.')
    password = serializers.CharField(write_only=True)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, validators=[_validate_password_strength]
    )


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True, validators=[_validate_password_strength]
    )


# Response shapes. These describe what the auth endpoints return so the OpenAPI
# schema is accurate; the views build the payloads themselves.

class DetailResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class LoginResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    csrf_token = serializers.CharField(
        help_text='Send as the X-CSRFToken header on unsafe requests.'
    )
    user = EmployeeSerializer()


class CsrfTokenResponseSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()
