from django.conf import settings
from django.db import models


class Warehouse(models.Model):
    """A storage location of a company."""

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='warehouses',
    )

    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)

    #: Receives the low stock alerts of this warehouse.
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='managed_warehouses',
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'warehouses'
        ordering = ['name']

        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name'],
                name='unique_warehouse_name_per_company',
            ),
        ]

    def __str__(self):
        return self.name
