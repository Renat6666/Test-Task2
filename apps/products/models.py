from django.db import models
from django.db.models import Q


class ProductQuerySet(models.QuerySet):
    """Queryset exposing the soft delete state explicitly."""

    def alive(self):
        """Only products that have not been soft deleted."""
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)


class Product(models.Model):
    """An article of a company.

    Products are **soft** deleted: an article that was shipped in the past must
    stay resolvable, otherwise the transaction history would break.
    """

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='products',
    )

    sku = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    #: Stock level below which a low stock alert is sent out.
    min_stock_level = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=0,
    )

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        db_table = 'products'
        ordering = ['name']

        constraints = [
            # A SKU is unique among the *live* products of a company, so a code
            # may be reused once the old article has been deleted.
            models.UniqueConstraint(
                fields=['company', 'sku'],
                condition=Q(is_deleted=False),
                name='unique_active_product_sku_per_company',
            ),
            models.CheckConstraint(
                condition=Q(base_price__gte=0),
                name='product_price_non_negative',
            ),
            models.CheckConstraint(
                condition=Q(min_stock_level__gte=0),
                name='product_min_stock_non_negative',
            ),
        ]

        indexes = [
            models.Index(fields=['company', 'is_deleted'], name='product_company_alive_idx'),
            models.Index(fields=['name'], name='product_name_idx'),
        ]

    def __str__(self):
        return f'{self.sku} - {self.name}'
