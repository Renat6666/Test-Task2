from rest_framework.routers import DefaultRouter

from apps.reports.views import ReportViewSet

router = DefaultRouter()
router.register('reports', ReportViewSet, basename='report')

urlpatterns = router.urls
