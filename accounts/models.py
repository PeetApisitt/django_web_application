from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    employee_code = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        verbose_name="รหัสพนักงาน",
    )