from rest_framework.routers import DefaultRouter

from apps.transactions.views import InventoryTransactionViewSet

router = DefaultRouter()
router.register('transactions', InventoryTransactionViewSet, basename='transaction')

urlpatterns = router.urls
