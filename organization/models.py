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