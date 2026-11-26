from django.db import models


class Company(models.Model):
    """A tenant. Every warehouse, product and transaction belongs to one."""

    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'companies'
        ordering = ['name']
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name
