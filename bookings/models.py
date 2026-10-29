from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class BookingRequest(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "แบบร่าง"
        PENDING_REVIEW = "pending_review", "รอการพิจารณา"
        PENDING_SIGNATURE = (
            "pending_signature",
            "รอหัวหน้าแผนกลงนาม",
        )
        APPROVED = "approved", "อนุมัติครบตามคำขอ"
        PARTIALLY_APPROVED = (
            "partially_approved",
            "อนุมัติบางรายชื่อ",
        )
        REJECTED = "rejected", "ปฏิเสธคำขอ"
        CANCELLED = "cancelled", "ยกเลิก"

    requesting_division = models.ForeignKey(
        "organization.Divisions",
        on_delete=models.PROTECT,
        related_name="outgoing_booking_requests",
        verbose_name="กองงานผู้ขอ",
    )

    source_division = models.ForeignKey(
        "organization.Divisions",
        on_delete=models.PROTECT,
        related_name="incoming_booking_requests",
        verbose_name="กองงานต้นสังกัด",
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_booking_requests",
        verbose_name="ผู้สร้างคำขอ",
    )

    purpose = models.TextField(
        verbose_name="เหตุผลในการขอใช้ชื่อ",
    )

    start_at = models.DateTimeField(
        verbose_name="วันเวลาเริ่มใช้งาน",
    )

    end_at = models.DateTimeField(
        verbose_name="วันเวลาสิ้นสุดการใช้งาน",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="สถานะคำขอ",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="วันที่สร้างคำขอ",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="วันที่แก้ไขล่าสุด",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "คำขอยืมพนักงาน"
        verbose_name_plural = "คำขอยืมพนักงาน"

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.requesting_division_id
            and self.source_division_id
            and self.requesting_division_id
            == self.source_division_id
        ):
            errors["source_division"] = (
                "กองงานผู้ขอต้องไม่ใช่กองงานต้นสังกัด "
                "ของกำลังพลที่ต้องการยืม"
            )

        if (
            self.start_at
            and self.end_at
            and self.end_at <= self.start_at
        ):
            errors["end_at"] = (
                "วันเวลาสิ้นสุดต้องอยู่หลังวันเวลาเริ่มต้น"
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"คำขอ #{self.pk} "
            f"{self.requesting_division} "
            f"ยืมจาก {self.source_division}"
        )


class BookingRequestItem(models.Model):

    class Status(models.TextChoices):
        PENDING_REVIEW = (
            "pending_review",
            "รอแอดมินพิจารณา",
        )
        ACCEPTED = (
            "accepted",
            "แอดมินยอมรับ",
        )
        REJECTED = (
            "rejected",
            "แอดมินปฏิเสธ",
        )
        APPROVED = (
            "approved",
            "อนุมัติแล้ว",
        )
        CANCELLED = (
            "cancelled",
            "ยกเลิก",
        )

    booking_request = models.ForeignKey(
        BookingRequest,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="คำขอ",
    )

    employee_code = models.CharField(
        max_length=30,
        verbose_name="รหัสพนักงาน",
    )

    employee_name_snapshot = models.CharField(
        max_length=150,
        verbose_name="ชื่อกำลังพล ณ เวลาที่ขอ",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
        verbose_name="สถานะรายชื่อ",
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_booking_items",
        verbose_name="ผู้พิจารณารายชื่อ",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="วันที่พิจารณา",
    )

    review_note = models.TextField(
        blank=True,
        verbose_name="หมายเหตุการพิจารณา",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="วันที่เพิ่มรายชื่อ",
    )

    class Meta:
        ordering = ["employee_code"]
        verbose_name = "รายชื่อในคำขอ"
        verbose_name_plural = "รายชื่อในคำขอ"

        constraints = [
            models.UniqueConstraint(
                fields=["booking_request", "employee_code"],
                name="uniq_employee_per_booking_request",
            ),
        ]

    def __str__(self):
        return (
            f"{self.employee_code} - "
            f"{self.employee_name_snapshot}"
        )