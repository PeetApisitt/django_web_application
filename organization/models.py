from django.conf import settings
from django.db import models

class Divisions(models.Model):
    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="รหัสกองงาน",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="ชื่อกองงาน",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="เปิดใช้งาน",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="วันที่สร้าง",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="วันที่แก้ไขล่าสุด",
    )

    class Meta:
        ordering = ["code"]
        verbose_name = "กองงาน"
        verbose_name_plural = "กองงาน"

    def __str__(self):
        return f"{self.code} - {self.name}"

class DivisionRoleAssignment(models.Model):

    class Role(models.TextChoices):
        ADMIN = "division_admin", "แอดมินกองงาน"
        DIRECTOR = "division_director", "ผู้อำนวยการกองงาน"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="division_role_assignments",
        verbose_name="ผู้ใช้งาน",
    )

    division = models.ForeignKey(
        Divisions,
        on_delete=models.PROTECT,
        related_name="role_assignments",
        verbose_name="กองงาน",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        verbose_name="บทบาท",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="เปิดใช้งาน",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="วันที่สร้าง",
    )

    class Meta:
        ordering = ["division__code", "role", "user__username"]

        verbose_name = "บทบาทประจำแผนก"
        verbose_name_plural = "บทบาทประจำแผนก"

        constraints = [
            models.UniqueConstraint(
                fields=["user", "division", "role"],
                name="uniq_user_dept_role",
            ),
        ]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.division.code} - "
            f"{self.get_role_display()}"
        )