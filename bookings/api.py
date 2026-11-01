from typing import List
from ninja import NinjaAPI, ModelSchema, Schema
from ninja.security import django_auth
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import get_object_or_404
from datetime import date
from django.db import transaction
from .models import BookingRequest, BookingRequestItem
from .services import (
    get_accessible_booking_requests,
    can_view_booking_request,
    submit_booking_request,
    review_booking_item,
    cancel_booking_request
)

# ประกาศ API Instance และบังคับให้ต้อง Login (อิง Session จากระบบ Django)
api = NinjaAPI(title="Employee Booking API", version="1.0.0", auth=django_auth)

# ==========================================
# 1. Schemas (สำหรับกำหนดหน้าตาข้อมูล JSON)
# ==========================================
class BookingItemSchema(ModelSchema):
    class Meta:
        model = BookingRequestItem
        fields = ['id', 'employee_code', 'employee_name_snapshot', 'status', 'review_note']

class BookingRequestSchema(ModelSchema):
    items: List[BookingItemSchema] = [] # ฝังข้อมูลพนักงานเข้าไปในคำขอหลัก
    
    class Meta:
        model = BookingRequest
        fields = ['id', 'requesting_division', 'source_division', 'requested_by', 'purpose', 'booking_date', 'status']

class ReviewActionSchema(Schema):
    action: str
    note: str = ""

class MessageSchema(Schema):
    message: str
    status: str = None

class ErrorSchema(Schema):
    error: str

class CreateItemIn(Schema):
    employee_code: str
    employee_name_snapshot: str

class CreateBookingIn(Schema):
    requesting_division_id: int
    source_division_id: int
    purpose: str
    booking_date: date
    items: List[CreateItemIn]
# ==========================================
# 2. Endpoints (เส้นทาง API)
# ==========================================
@api.get("/bookings/", response=List[BookingRequestSchema])
def list_bookings(request):
    """ดึงรายการคำขอทั้งหมดที่ผู้ใช้มีสิทธิ์มองเห็น"""
    return get_accessible_booking_requests(request.user)

@api.get("/bookings/{request_id}/", response={200: BookingRequestSchema, 403: ErrorSchema, 404: ErrorSchema})
def get_booking_detail(request, request_id: int):
    """ดูรายละเอียดคำขอรายตัว"""
    if not can_view_booking_request(request.user, request_id):
        return 403, {"error": "คุณไม่มีสิทธิ์เข้าถึงคำขอนี้"}
    
    booking = get_object_or_404(BookingRequest, pk=request_id)
    return 200, booking

@api.post("/bookings/{request_id}/submit/", response={200: MessageSchema, 400: ErrorSchema})
def submit_booking(request, request_id: int):
    """ส่งคำขอยืมพนักงาน"""
    try:
        result = submit_booking_request(request_id)
        return 200, {"message": "ส่งคำขอสำเร็จ", "status": result.status}
    except ValidationError as e:
        return 400, {"error": str(e.message if hasattr(e, 'message') else e)}

@api.post("/bookings/items/{item_id}/review/", response={200: MessageSchema, 400: ErrorSchema, 403: ErrorSchema})
def review_item(request, item_id: int, payload: ReviewActionSchema):
    """แอดมินพิจารณารายชื่อพนักงาน (ระบุ action เป็น 'ACCEPT' หรือ 'REJECT')"""
    try:
        result = review_booking_item(item_id, request.user, payload.action, payload.note)
        return 200, {"message": f"ทำรายการ {payload.action} สำเร็จ", "status": result.status}
    except PermissionDenied as e:
        return 403, {"error": str(e)}
    except ValidationError as e:
        return 400, {"error": str(e.message if hasattr(e, 'message') else e)}

@api.delete("/bookings/{request_id}/cancel/", response={200: MessageSchema, 400: ErrorSchema, 403: ErrorSchema})
def cancel_booking(request, request_id: int):
    """ยกเลิกคำขอโดยผู้สร้าง"""
    try:
        result = cancel_booking_request(request_id, request.user)
        return 200, {"message": "ยกเลิกคำขอสำเร็จ", "status": result.status}
    except PermissionDenied as e:
        return 403, {"error": str(e)}
    except ValidationError as e:
        return 400, {"error": str(e.message if hasattr(e, 'message') else e)}
    
@api.post("/bookings/", response={201: MessageSchema, 400: ErrorSchema})
@transaction.atomic
def create_booking(request, payload: CreateBookingIn):
    """สร้างคำขอยืมพนักงานใหม่ (ระบบจะบันทึกเป็นฉบับร่าง DRAFT อัตโนมัติ)"""
    try:
        booking = BookingRequest.objects.create(
            requesting_division_id=payload.requesting_division_id,
            source_division_id=payload.source_division_id,
            requested_by=request.user,
            purpose=payload.purpose,
            booking_date=payload.booking_date,
            status=BookingRequest.Status.DRAFT
        )
        
        for item in payload.items:
            BookingRequestItem.objects.create(
                booking_request=booking,
                employee_code=item.employee_code,
                employee_name_snapshot=item.employee_name_snapshot,
                status=BookingRequestItem.Status.DRAFT
            )
        return 201, {"message": f"สร้างคำขอแบบร่างสำเร็จ (ID: {booking.id})", "status": booking.status}
    except Exception as e:
        return 400, {"error": str(e)}