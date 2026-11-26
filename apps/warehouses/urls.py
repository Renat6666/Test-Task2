from rest_framework.routers import DefaultRouter

from apps.warehouses.views import WarehouseViewSet

router = DefaultRouter()
router.register('warehouses', WarehouseViewSet, basename='warehouse')

urlpatterns = router.urls
