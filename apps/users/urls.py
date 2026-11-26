from rest_framework.routers import DefaultRouter

from apps.users.views import AuthViewSet, EmployeeViewSet

router = DefaultRouter()
router.register('auth', AuthViewSet, basename='auth')
router.register('employees', EmployeeViewSet, basename='employee')

urlpatterns = router.urls
