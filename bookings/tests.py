from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from organization.models import Divisions, DivisionRoleAssignment

from .models import (
    BookingRequest,
    BookingRequestItem,
    EmployeeBookingReservation,
)

from .services import (
    submit_booking_request, 
    review_booking_item,
    approve_booking_request,
    cancel_booking_request,
    get_accessible_booking_requests,
    can_view_booking_request
)


class DailyBookingTests(TestCase):

    def setUp(self):
        # สร้าง Users แต่ละบทบาท
        self.user = User.objects.create_user(username="test_user", password="test_password")
        self.admin_b = User.objects.create_user(username="admin_b", password="test_password")
        self.director_b = User.objects.create_user(username="director_b", password="test_password")
        self.other_user = User.objects.create_user(username="other_user", password="test_password")
        self.superuser = User.objects.create_superuser(username="super", password="test_password")

        self.division_a = Divisions.objects.create(code="D01", name="Division A")
        self.division_b = Divisions.objects.create(code="D02", name="Division B")
        self.division_c = Divisions.objects.create(code="D03", name="Division C")
        
        # ผูกสิทธิ์ Admin และ Director ให้แผนก B
        DivisionRoleAssignment.objects.create(
            user=self.admin_b,
            division=self.division_b,
            role=DivisionRoleAssignment.Role.ADMIN,
            is_active=True
        )
        DivisionRoleAssignment.objects.create(
            user=self.director_b,
            division=self.division_b,
            role=DivisionRoleAssignment.Role.DIRECTOR,
            is_active=True
        )

        self.booking_date = timezone.localdate() + timedelta(days=1)

    def create_request(self, requesting_division, employee_code, booking_date=None, requested_by=None):
        request = BookingRequest.objects.create(
            requesting_division=requesting_division,
            source_division=self.division_b,
            requested_by=requested_by or self.user,
            purpose="งานสำคัญประจำแผนก",
            booking_date=(booking_date or self.booking_date),
        )
        BookingRequestItem.objects.create(
            booking_request=request,
            employee_code=employee_code,
            employee_name_snapshot="Test Employee",
        )
        return request

    def create_multi_item_request(self, requesting_division, employee_codes):
        request = BookingRequest.objects.create(
            requesting_division=requesting_division,
            source_division=self.division_b,
            requested_by=self.user,
            purpose="งานสำคัญประจำแผนก",
            booking_date=self.booking_date,
        )
        for code in employee_codes:
            BookingRequestItem.objects.create(
                booking_request=request,
                employee_code=code,
                employee_name_snapshot=f"Employee {code}",
            )
        return request

    # ----------------------------------------------------
    # Submission Tests
    # ----------------------------------------------------

    def test_successful_daily_booking(self):
        request = self.create_request(self.division_a, "TEST001")
        result = submit_booking_request(request.pk)
        self.assertEqual(result.status, BookingRequest.Status.PENDING_REVIEW)

    def test_duplicate_booking_same_day(self):
        request_1 = self.create_request(self.division_a, "TEST002")
        request_2 = self.create_request(self.division_c, "TEST002")
        submit_booking_request(request_1.pk)
        with self.assertRaises(ValidationError):
            submit_booking_request(request_2.pk)

    def test_booking_same_employee_next_day(self):
        request_1 = self.create_request(self.division_a, "TEST003")
        request_2 = self.create_request(self.division_c, "TEST003", self.booking_date + timedelta(days=1))
        submit_booking_request(request_1.pk)
        result = submit_booking_request(request_2.pk)
        self.assertEqual(result.status, BookingRequest.Status.PENDING_REVIEW)

    def test_request_without_employee(self):
        request = BookingRequest.objects.create(
            requesting_division=self.division_a,
            source_division=self.division_b,
            requested_by=self.user,
            purpose="งานทดสอบ",
            booking_date=self.booking_date,
        )
        with self.assertRaises(ValidationError):
            submit_booking_request(request.pk)

    # ----------------------------------------------------
    # Review Workflow & Auto-Evaluation Tests
    # ----------------------------------------------------

    def test_review_item_accept_success(self):
        request = self.create_request(self.division_a, "EMP001")
        submit_booking_request(request.pk)
        item = request.items.first()
        review_booking_item(item.pk, self.admin_b, "ACCEPT")
        
        request.refresh_from_db()
        self.assertEqual(request.status, BookingRequest.Status.PENDING_SIGNATURE)

    def test_evaluate_status_all_rejected(self):
        request = self.create_multi_item_request(self.division_a, ["EMP20", "EMP21"])
        submit_booking_request(request.pk)
        item1 = request.items.get(employee_code="EMP20")
        item2 = request.items.get(employee_code="EMP21")
        review_booking_item(item1.pk, self.admin_b, "REJECT", "note")
        review_booking_item(item2.pk, self.admin_b, "REJECT", "note")
        request.refresh_from_db()
        self.assertEqual(request.status, BookingRequest.Status.REJECTED)

    # ----------------------------------------------------
    # Phase 3: Review Workflow & Auto-Evaluation Tests 
    # ----------------------------------------------------

    def test_review_item_accept_success(self):
        request = self.create_request(self.division_a, "EMP001")
        submit_booking_request(request.pk)
        item = request.items.first()
        review_booking_item(item.pk, self.admin_b, "ACCEPT")
        
        request.refresh_from_db()
        # มีคนเดียวและ Accept ไปแล้ว สถานะต้องจบที่ APPROVED ทันที
        self.assertEqual(request.status, BookingRequest.Status.APPROVED)
        # สถานะรายชื่อต้องเปลี่ยนจาก ACCEPTED เป็น APPROVED อัตโนมัติ
        item.refresh_from_db()
        self.assertEqual(item.status, BookingRequestItem.Status.APPROVED)

    def test_evaluate_status_all_rejected(self):
        request = self.create_multi_item_request(self.division_a, ["EMP20", "EMP21"])
        submit_booking_request(request.pk)
        item1 = request.items.get(employee_code="EMP20")
        item2 = request.items.get(employee_code="EMP21")
        review_booking_item(item1.pk, self.admin_b, "REJECT", "note")
        review_booking_item(item2.pk, self.admin_b, "REJECT", "note")
        request.refresh_from_db()
        self.assertEqual(request.status, BookingRequest.Status.REJECTED)

    def test_evaluate_status_mixed_accepted_and_rejected(self):
        request = self.create_multi_item_request(self.division_a, ["EMP40", "EMP41"])
        submit_booking_request(request.pk)
        item1 = request.items.get(employee_code="EMP40")
        item2 = request.items.get(employee_code="EMP41")
        
        review_booking_item(item1.pk, self.admin_b, "ACCEPT")
        review_booking_item(item2.pk, self.admin_b, "REJECT", "note")
        
        request.refresh_from_db()
        # ผ่านแค่บางคน สถานะต้องเป็น PARTIALLY_APPROVED ทันที
        self.assertEqual(request.status, BookingRequest.Status.PARTIALLY_APPROVED)

    # ----------------------------------------------------
    # Phase 4: Cancellation and Reservation Release Tests
    # ----------------------------------------------------

    def test_cancel_booking_success(self):
        request = self.create_multi_item_request(self.division_a, ["CAN01", "CAN02"])
        submit_booking_request(request.pk)
        cancelled_req = cancel_booking_request(request.pk, self.user)
        self.assertEqual(cancelled_req.status, BookingRequest.Status.CANCELLED)
        res_count = EmployeeBookingReservation.objects.filter(
            employee_code__in=["CAN01", "CAN02"], 
            booking_date=self.booking_date
        ).count()
        self.assertEqual(res_count, 0)

    def test_cancel_booking_unauthorized(self):
        request = self.create_request(self.division_a, "CAN03")
        submit_booking_request(request.pk)
        with self.assertRaises(PermissionDenied):
            cancel_booking_request(request.pk, self.admin_b)

    def test_cancel_booking_invalid_status(self):
        request = self.create_request(self.division_a, "CAN04")
        submit_booking_request(request.pk)
        item = request.items.first()
        review_booking_item(item.pk, self.admin_b, "REJECT", "ไม่ว่าง")
        with self.assertRaises(ValidationError):
            cancel_booking_request(request.pk, self.user)

    # ----------------------------------------------------
    # Phase 5: Authentication and Authorization Tests
    # ----------------------------------------------------

    def test_authorization_visibility_rules(self):
        # สร้างคำขอโดย self.user ส่งไปที่ แผนก B
        req1 = self.create_request(self.division_a, "AUTH01", requested_by=self.user)
        # สร้างคำขอโดย self.other_user ส่งไปที่ แผนก B
        req2 = self.create_request(self.division_a, "AUTH02", requested_by=self.other_user)

        # 1. ผู้สร้างคำขอต้องเห็นแค่ของตัวเอง
        user_reqs = get_accessible_booking_requests(self.user)
        self.assertIn(req1, user_reqs)
        self.assertNotIn(req2, user_reqs)
        self.assertTrue(can_view_booking_request(self.user, req1.pk))
        self.assertFalse(can_view_booking_request(self.user, req2.pk))

        # 2. Admin แผนกปลายทาง (B) ต้องเห็นทั้งหมดที่ส่งมาแผนกตัวเอง
        admin_reqs = get_accessible_booking_requests(self.admin_b)
        self.assertIn(req1, admin_reqs)
        self.assertIn(req2, admin_reqs)
        self.assertTrue(can_view_booking_request(self.admin_b, req1.pk))

        # 3. Director แผนกปลายทาง (B) ต้องเห็นทั้งหมดที่ส่งมาแผนกตัวเอง
        director_reqs = get_accessible_booking_requests(self.director_b)
        self.assertIn(req1, director_reqs)
        self.assertIn(req2, director_reqs)
        self.assertTrue(can_view_booking_request(self.director_b, req1.pk))

        # 4. Superuser ต้องเห็นทั้งหมด
        super_reqs = get_accessible_booking_requests(self.superuser)
        self.assertIn(req1, super_reqs)
        self.assertIn(req2, super_reqs)
        self.assertTrue(can_view_booking_request(self.superuser, req1.pk))

        # 5. User อื่นที่ไม่เกี่ยวข้อง ต้องไม่เห็นคำขอใดๆ ที่ไม่ได้สร้างเอง
        # (สมมติสร้าง User ใหม่ที่ไม่มีคำขอเลย)
        third_user = User.objects.create_user(username="third", password="pwd")
        third_reqs = get_accessible_booking_requests(third_user)
        self.assertEqual(third_reqs.count(), 0)
        self.assertFalse(can_view_booking_request(third_user, req1.pk))