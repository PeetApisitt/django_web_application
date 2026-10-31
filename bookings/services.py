from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from organization.models import DivisionRoleAssignment
from .models import (
    BookingRequest,
    BookingRequestItem,
    EmployeeBookingReservation,
)


@transaction.atomic
def submit_booking_request(request_id):
    try:
        booking_request = (
            BookingRequest.objects
            .select_for_update()
            .get(pk=request_id)
        )
    except BookingRequest.DoesNotExist:
        raise ValidationError("ไม่พบคำขอจองที่ระบุ")

    if booking_request.status != BookingRequest.Status.DRAFT:
        raise ValidationError("สามารถส่งคำขอได้เฉพาะรายการแบบร่าง")

    if not booking_request.booking_date:
        raise ValidationError("กรุณาระบุวันที่ต้องการใช้พนักงาน")

    if (
        booking_request.requesting_division_id
        == booking_request.source_division_id
    ):
        raise ValidationError("ไม่สามารถขอยืมพนักงานจากแผนกเดียวกันได้")

    items = list(
        BookingRequestItem.objects
        .select_for_update()
        .filter(booking_request=booking_request)
        .order_by("employee_code")
    )

    if not items:
        raise ValidationError("กรุณาเพิ่มรายชื่อพนักงานก่อนส่งคำขอ")

    employee_codes = []
    for item in items:
        code = item.employee_code.strip()
        if not code:
            raise ValidationError("พบรายการที่ไม่ได้ระบุรหัสพนักงาน")
        employee_codes.append(code)

    if len(employee_codes) != len(set(employee_codes)):
        raise ValidationError("พบรหัสพนักงานซ้ำภายในคำขอเดียวกัน")

    for item, code in zip(items, employee_codes):
        reservation, created = (
            EmployeeBookingReservation.objects.get_or_create(
                employee_code=code,
                booking_date=booking_request.booking_date,
                defaults={"booking_request_item": item},
            )
        )

        if not created and reservation.booking_request_item_id != item.pk:
            raise ValidationError(
                f"พนักงาน {code} ถูกจองแล้วในวันที่ {booking_request.booking_date}"
            )

        item.employee_code = code
        item.status = BookingRequestItem.Status.PENDING_REVIEW
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

    booking_request.status = BookingRequest.Status.PENDING_REVIEW
    booking_request.save(update_fields=["status", "updated_at"])

    return booking_request


@transaction.atomic
def evaluate_booking_request_status(request_id):
    try:
        booking_request = BookingRequest.objects.select_for_update().get(pk=request_id)
    except BookingRequest.DoesNotExist:
        return None

    if booking_request.status != BookingRequest.Status.PENDING_REVIEW:
        return booking_request

    items = booking_request.items.all()
    
    has_pending = False
    has_accepted = False

    for item in items:
        if item.status == BookingRequestItem.Status.PENDING_REVIEW:
            has_pending = True
            break
        elif item.status == BookingRequestItem.Status.ACCEPTED:
            has_accepted = True

    if has_pending:
        return booking_request

    if has_accepted:
        booking_request.status = BookingRequest.Status.PENDING_SIGNATURE
    else:
        booking_request.status = BookingRequest.Status.REJECTED

    booking_request.save(update_fields=['status', 'updated_at'])
    return booking_request


@transaction.atomic
def review_booking_item(item_id, reviewer, action, note=""):
    try:
        item = (
            BookingRequestItem.objects
            .select_for_update()
            .select_related("booking_request", "booking_request__source_division")
            .get(pk=item_id)
        )
    except BookingRequestItem.DoesNotExist:
        raise ValidationError("ไม่พบรายการพนักงานที่ต้องการพิจารณา")

    if item.status != BookingRequestItem.Status.PENDING_REVIEW:
        raise ValidationError("ไม่สามารถพิจารณารายการนี้ได้ (สถานะปัจจุบันไม่ถูกต้อง)")

    source_division = item.booking_request.source_division
    is_admin = DivisionRoleAssignment.objects.filter(
        user=reviewer,
        division=source_division,
        role=DivisionRoleAssignment.Role.ADMIN,
        is_active=True
    ).exists()

    if not is_admin:
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการพิจารณาคำขอของแผนกต้นสังกัดนี้")

    if action not in ["ACCEPT", "REJECT"]:
        raise ValidationError("การกระทำไม่ถูกต้อง (ต้องเป็น ACCEPT หรือ REJECT)")

    if action == "REJECT":
        if not note or not note.strip():
            raise ValidationError("กรุณาระบุหมายเหตุเมื่อทำการปฏิเสธพนักงาน")
        
        item.status = BookingRequestItem.Status.REJECTED
        EmployeeBookingReservation.objects.filter(booking_request_item=item).delete()
        
    elif action == "ACCEPT":
        item.status = BookingRequestItem.Status.ACCEPTED

    item.reviewed_by = reviewer
    item.reviewed_at = timezone.now()
    item.review_note = note.strip() if note else ""

    item.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_note",
        ]
    )

    evaluate_booking_request_status(item.booking_request_id)

    return item


@transaction.atomic
def approve_booking_request(request_id, director, signature_text, note=""):
    try:
        booking_request = BookingRequest.objects.select_for_update().get(pk=request_id)
    except BookingRequest.DoesNotExist:
        raise ValidationError("ไม่พบคำขอจองที่ระบุ")

    if booking_request.status != BookingRequest.Status.PENDING_SIGNATURE:
        raise ValidationError("ไม่สามารถอนุมัติได้ (คำขอไม่ได้อยู่ในสถานะรอลงนาม)")

    if not signature_text or not signature_text.strip():
        raise ValidationError("กรุณาระบุข้อมูลลายมือชื่ออิเล็กทรอนิกส์ (E-signature)")

    is_director = DivisionRoleAssignment.objects.filter(
        user=director,
        division=booking_request.source_division,
        role=DivisionRoleAssignment.Role.DIRECTOR,
        is_active=True
    ).exists()

    if not is_director:
        raise PermissionDenied("คุณไม่มีสิทธิ์ในการอนุมัติคำขอของแผนกต้นสังกัดนี้")

    items = BookingRequestItem.objects.select_for_update().filter(booking_request=booking_request)
    
    approved_count = 0
    rejected_count = 0

    for item in items:
        if item.status == BookingRequestItem.Status.ACCEPTED:
            item.status = BookingRequestItem.Status.APPROVED
            item.save(update_fields=['status'])
            approved_count += 1
        elif item.status == BookingRequestItem.Status.REJECTED:
            rejected_count += 1

    if approved_count > 0 and rejected_count == 0:
        booking_request.status = BookingRequest.Status.APPROVED
    elif approved_count > 0 and rejected_count > 0:
        booking_request.status = BookingRequest.Status.PARTIALLY_APPROVED
    else:
        booking_request.status = BookingRequest.Status.REJECTED

    booking_request.approved_by = director
    booking_request.approved_at = timezone.now()
    booking_request.approval_note = note.strip() if note else ""
    booking_request.signature_text = signature_text.strip()
    
    booking_request.save(
        update_fields=[
            'status', 
            'approved_by', 
            'approved_at', 
            'approval_note', 
            'signature_text', 
            'updated_at'
        ]
    )

    return booking_request


@transaction.atomic
def cancel_booking_request(request_id, requested_user):
    try:
        booking_request = BookingRequest.objects.select_for_update().get(pk=request_id)
    except BookingRequest.DoesNotExist:
        raise ValidationError("ไม่พบคำขอจองที่ระบุ")

    if booking_request.requested_by != requested_user:
        raise PermissionDenied("คุณไม่มีสิทธิ์ยกเลิกคำขอนี้ (ต้องเป็นผู้สร้างคำขอเท่านั้น)")

    if booking_request.status in [
        BookingRequest.Status.CANCELLED, 
        BookingRequest.Status.REJECTED
    ]:
        raise ValidationError(f"ไม่สามารถยกเลิกคำขอที่อยู่ในสถานะ '{booking_request.get_status_display()}' ได้")

    items = BookingRequestItem.objects.select_for_update().filter(booking_request=booking_request)
    
    for item in items:
        item.status = BookingRequestItem.Status.CANCELLED
        item.save(update_fields=['status'])
        EmployeeBookingReservation.objects.filter(booking_request_item=item).delete()

    booking_request.status = BookingRequest.Status.CANCELLED
    booking_request.save(update_fields=['status', 'updated_at'])

    return booking_request


# --- Phase 5: Authentication and Authorization Services ---

def get_accessible_booking_requests(user):
    """
    ดึงข้อมูลคำขอยืมพนักงานทั้งหมดที่ผู้ใช้งานมีสิทธิ์มองเห็น
    """
    if user.is_superuser:
        return BookingRequest.objects.all()

    # 1. สิทธิ์ในฐานะผู้ขอยืม (เห็นคำขอที่ตัวเองเป็นคนสร้าง)
    q_requested_by = Q(requested_by=user)

    # 2. สิทธิ์ในฐานะ Admin หรือ Director ของแผนกต้นสังกัด (เห็นคำขอที่ส่งมาที่แผนก)
    user_managed_divisions = DivisionRoleAssignment.objects.filter(
        user=user,
        is_active=True,
        role__in=[DivisionRoleAssignment.Role.ADMIN, DivisionRoleAssignment.Role.DIRECTOR]
    ).values_list('division_id', flat=True)

    q_source_division = Q(source_division_id__in=user_managed_divisions)

    return BookingRequest.objects.filter(q_requested_by | q_source_division).distinct()


def can_view_booking_request(user, request_id):
    """
    ตรวจสอบสิทธิ์ว่าผู้ใช้งานสามารถดูรายละเอียดคำขอนี้ได้หรือไม่
    """
    try:
        booking_request = BookingRequest.objects.get(pk=request_id)
    except BookingRequest.DoesNotExist:
        return False

    if user.is_superuser:
        return True

    if booking_request.requested_by == user:
        return True

    is_manager = DivisionRoleAssignment.objects.filter(
        user=user,
        division=booking_request.source_division,
        role__in=[DivisionRoleAssignment.Role.ADMIN, DivisionRoleAssignment.Role.DIRECTOR],
        is_active=True
    ).exists()

    return is_manager