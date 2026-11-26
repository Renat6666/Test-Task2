from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """An employee of a company.

    Authentication stays on Django's standard stack (session + cookies); the
    only additions are a unique email (needed for the password reset flow) and
    the company the employee works for.
    """

    email = models.EmailField(unique=True)

    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.PROTECT,
        related_name='employees',
        null=True,
        blank=True,
    )

    class Meta(AbstractUser.Meta):
        db_table = 'users'

    def __str__(self):
        return self.get_username()
