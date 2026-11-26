from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.viewsets import CompanyScopedQuerysetMixin
from apps.companies import selectors
from apps.companies.models import Company
from apps.companies.serializers import CompanySerializer


@extend_schema_view(
    list=extend_schema(
        summary='List companies',
        description='Only ever returns your own company.',
    ),
    retrieve=extend_schema(summary='Get a company'),
)
@extend_schema(tags=['companies'])
class CompanyViewSet(CompanyScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """The company of the signed-in employee.

    Companies are created during registration, so this resource is read only.
    """

    queryset = Company.objects.none()  # schema generation only
    serializer_class = CompanySerializer
    pagination_class = None
    filter_backends = []

    def get_company_queryset(self):
        return selectors.company_list(company=self.company)

    @extend_schema(
        summary='Your company',
        description='Shortcut for "my company" that needs no id.',
        responses={200: CompanySerializer},
    )
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Shortcut for "my company" that needs no id."""
        return Response(self.get_serializer(self.company).data)
