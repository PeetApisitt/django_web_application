from django.core.exceptions import ValidationError
from django.db import transaction
from .models import (
    BookingRequest,
    BookingRequestItem,
    EmployeeBookingReservation,
)


@transaction.atomic
def submit_booking_request(request_id):
    """
    ส่งคำขอจองพนักงานเข้าสู่ระบบ

    กฎ:
    1. รับเฉพาะคำขอสถานะ DRAFT
    2. คำขอต้องมีรายชื่อพนักงาน
    3. พนักงานหนึ่งคนจองได้หนึ่งคำขอต่อหนึ่งวัน
    4. สร้าง Reservation ภายใน Transaction
    5. เปลี่ยนสถานะเป็น PENDING_REVIEW
    """

    # 1. ค้นหาและ Lock คำขอ
    try:
        booking_request = (
            BookingRequest.objects
            .select_for_update()
            .get(pk=request_id)
        )

    except BookingRequest.DoesNotExist:
        raise ValidationError(
            "ไม่พบคำขอจองที่ระบุ"
        )

    # 2. ตรวจสอบสถานะ
    if booking_request.status != BookingRequest.Status.DRAFT:
        raise ValidationError(
            "สามารถส่งคำขอได้เฉพาะรายการแบบร่าง"
        )

    # 3. ตรวจสอบวันที่
    if not booking_request.booking_date:
        raise ValidationError(
            "กรุณาระบุวันที่ต้องการใช้พนักงาน"
        )

    # 4. ตรวจสอบแผนก
    if (
        booking_request.requesting_division_id
        == booking_request.source_division_id
    ):
        raise ValidationError(
            "ไม่สามารถขอยืมพนักงานจากแผนกเดียวกันได้"
        )

    # 5. ดึงรายชื่อทั้งหมดในคำขอ
    items = list(
        BookingRequestItem.objects
        .select_for_update()
        .filter(
            booking_request=booking_request
        )
        .order_by("employee_code")
    )

    if not items:
        raise ValidationError(
            "กรุณาเพิ่มรายชื่อพนักงานก่อนส่งคำขอ"
        )

    # 6. ตรวจสอบและปรับรูปแบบรหัสพนักงาน
    employee_codes = []

    for item in items:

        code = item.employee_code.strip()

        if not code:
            raise ValidationError(
                "พบรายการที่ไม่ได้ระบุรหัสพนักงาน"
            )

        employee_codes.append(code)

    # ตรวจสอบรหัสพนักงานซ้ำภายในคำขอ
    if len(employee_codes) != len(set(employee_codes)):
        raise ValidationError(
            "พบรหัสพนักงานซ้ำภายในคำขอเดียวกัน"
        )

    # 7. สร้าง Reservation สำหรับพนักงานแต่ละคน
    for item, code in zip(items, employee_codes):

        reservation, created = (
            EmployeeBookingReservation.objects.get_or_create(
                employee_code=code,
                booking_date=booking_request.booking_date,

                defaults={
                    "booking_request_item": item,
                },
            )
        )

        # หากมี Reservation อยู่ก่อนแล้ว
        # และเป็นของคำขออื่น ให้ปฏิเสธ
        if (
            not created
            and reservation.booking_request_item_id != item.pk
        ):
            raise ValidationError(
                f"พนักงาน {code} ถูกจองแล้วในวันที่ "
                f"{booking_request.booking_date}"
            )

        # ปรับรหัสพนักงานให้ไม่มีช่องว่างหัวท้าย
        item.employee_code = code

        # เปลี่ยนสถานะรายชื่อ
        item.status = (
            BookingRequestItem.Status.PENDING_REVIEW
        )

        item.reviewed_by = None
        item.reviewed_at = None
        item.review_note = ""

        item.save(
            update_fields=[
                "employee_code",
                "status",
                "reviewed_by",
                "reviewed_at",
                "review_note",
            ]
        )

    # 8. เปลี่ยนสถานะคำขอ
    booking_request.status = (
        BookingRequest.Status.PENDING_REVIEW
    )

    booking_request.save(
        update_fields=[
            "status",
            "updated_at",
        ]
    )

    return booking_request
