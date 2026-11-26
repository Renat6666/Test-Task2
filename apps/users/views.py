from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.common.permissions import IsCompanyEmployee
from apps.common.viewsets import CompanyScopedQuerysetMixin
from apps.users import selectors, services
from apps.users.models import User
from apps.users.serializers import (
    CsrfTokenResponseSerializer,
    DetailResponseSerializer,
    EmployeeSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
)
from apps.users.throttles import AuthThrottle


@extend_schema(tags=['auth'])
class AuthViewSet(viewsets.ViewSet):
    """Registration, session login/logout and password management.

    Authentication is Django's standard session + cookie stack. Unsafe requests
    made with a session cookie must carry the ``X-CSRFToken`` header; call
    ``GET /api/auth/csrf/`` once to receive the ``csrftoken`` cookie.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @extend_schema(
        summary='Register an employee',
        description=(
            'Creates an employee and attaches them to a company. The company '
            'is created when `company_name` is new, otherwise the employee '
            'joins the existing one. Does not open a session -- call '
            '`/api/auth/login/` next.'
        ),
        request=RegisterSerializer,
        responses={
            201: EmployeeSerializer,
            400: OpenApiResponse(
                description='Validation error: username/email taken, or weak password'
            ),
        },
    )
    @action(detail=False, methods=['post'])
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = services.register_employee(**serializer.validated_data)
        return Response(EmployeeSerializer(user).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Sign in',
        description=(
            'Opens a session and sets the `inventory_sessionid` cookie. '
            '`login` accepts either the username or the email address. The '
            'returned `csrf_token` is what unsafe requests need in the '
            '`X-CSRFToken` header.'
        ),
        request=LoginSerializer,
        responses={
            200: LoginResponseSerializer,
            403: OpenApiResponse(description='Invalid credentials or disabled account'),
        },
    )
    @action(detail=False, methods=['post'])
    def login(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = services.login_employee(request=request, **serializer.validated_data)
        return Response({
            'detail': 'Signed in.',
            'csrf_token': get_token(request),
            'user': EmployeeSerializer(user).data,
        })

    @extend_schema(
        summary='Sign out',
        description='Flushes the session and clears the session cookie.',
        request=None,
        responses={200: DetailResponseSerializer},
    )
    @action(
        detail=False,
        methods=['post'],
        permission_classes=[IsAuthenticated],
        throttle_classes=[],
    )
    def logout(self, request):
        services.logout_employee(request=request)
        return Response({'detail': 'Signed out.'})

    @extend_schema(
        summary='The signed-in employee',
        responses={200: EmployeeSerializer},
    )
    @action(
        detail=False,
        methods=['get'],
        permission_classes=[IsAuthenticated],
        throttle_classes=[],
    )
    def me(self, request):
        return Response(EmployeeSerializer(request.user).data)

    @extend_schema(
        summary='Request a password reset',
        description=(
            'Emails a reset link. The response is deliberately identical for '
            'known and unknown addresses, so the endpoint cannot be used to '
            'enumerate accounts.'
        ),
        request=PasswordResetRequestSerializer,
        responses={200: DetailResponseSerializer},
    )
    @action(detail=False, methods=['post'], url_path='password-reset')
    def password_reset(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        services.request_password_reset(**serializer.validated_data)
        # Deliberately identical for known and unknown addresses.
        return Response({'detail': 'If that address exists, a reset link has been sent.'})

    @extend_schema(
        summary='Set a new password from a reset link',
        description=(
            'Takes the `uid` and `token` from the emailed link. A token works '
            'once and expires after `PASSWORD_RESET_TIMEOUT`.'
        ),
        request=PasswordResetConfirmSerializer,
        responses={
            200: DetailResponseSerializer,
            400: OpenApiResponse(description='Invalid or expired link, or weak password'),
        },
    )
    @action(detail=False, methods=['post'], url_path='password-reset/confirm')
    def password_reset_confirm(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        services.confirm_password_reset(**serializer.validated_data)
        return Response({'detail': 'Password updated.'})

    @extend_schema(
        summary='Change your own password',
        request=PasswordChangeSerializer,
        responses={
            200: DetailResponseSerializer,
            400: OpenApiResponse(description='Wrong current password, or weak new one'),
        },
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='password-change',
        permission_classes=[IsAuthenticated],
        throttle_classes=[],
    )
    def password_change(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        services.change_password(user=request.user, **serializer.validated_data)
        return Response({'detail': 'Password updated.'})

    @extend_schema(
        summary='Get a CSRF token',
        description=(
            'Sets the `csrftoken` cookie and returns the token. Needed before '
            'any unsafe request made with a session cookie.'
        ),
        responses={200: CsrfTokenResponseSerializer},
    )
    @method_decorator(ensure_csrf_cookie)
    @action(detail=False, methods=['get'], throttle_classes=[])
    def csrf(self, request):
        """Hand out the CSRF cookie/token used for unsafe requests."""
        return Response({'csrf_token': get_token(request)})


@extend_schema_view(
    list=extend_schema(summary='List colleagues'),
    retrieve=extend_schema(summary='Get a colleague'),
)
@extend_schema(tags=['employees'])
class EmployeeViewSet(CompanyScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Colleagues of the signed-in employee (used to pick warehouse managers)."""

    permission_classes = [IsCompanyEmployee]
    queryset = User.objects.none()  # schema generation only
    serializer_class = EmployeeSerializer
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'date_joined']
    ordering = ['username']

    def get_company_queryset(self):
        return selectors.employee_list(company=self.company)
