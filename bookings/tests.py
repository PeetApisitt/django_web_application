
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from accounts.models import User
from organization.models import Divisions

from .models import (
    BookingRequest,
    BookingRequestItem,
    EmployeeBookingReservation,
)

from .services import submit_booking_request


class DailyBookingTests(TestCase):

    def setUp(self):

        self.user = User.objects.create_user(
            username="test_user",
            password="test_password",
        )

        self.division_a = Divisions.objects.create(
            code="D01",
            name="Division A",
        )

        self.division_b = Divisions.objects.create(
            code="D02",
            name="Division B",
        )

        self.division_c = Divisions.objects.create(
            code="D03",
            name="Division C",
        )

        self.booking_date = (
            timezone.localdate() + timedelta(days=1)
        )

    def create_request(
        self,
        requesting_division,
        employee_code,
        booking_date=None,
    ):

        request = BookingRequest.objects.create(
            requesting_division=requesting_division,
            source_division=self.division_b,
            requested_by=self.user,
            purpose="งานสำคัญประจำแผนก",
            booking_date=(
                booking_date or self.booking_date
            ),
        )

        BookingRequestItem.objects.create(
            booking_request=request,
            employee_code=employee_code,
            employee_name_snapshot="Test Employee",
        )

        return request

    def test_successful_daily_booking(self):

        request = self.create_request(
            self.division_a,
            "TEST001",
        )

        result = submit_booking_request(request.pk)

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            BookingRequest.Status.PENDING_REVIEW,
        )

        self.assertTrue(
            EmployeeBookingReservation.objects.filter(
                employee_code="TEST001",
                booking_date=self.booking_date,
            ).exists()
        )

    def test_duplicate_booking_same_day(self):

        request_1 = self.create_request(
            self.division_a,
            "TEST002",
        )

        request_2 = self.create_request(
            self.division_c,
            "TEST002",
        )

        submit_booking_request(request_1.pk)

        with self.assertRaises(ValidationError):
            submit_booking_request(request_2.pk)

        request_2.refresh_from_db()

        self.assertEqual(
            request_2.status,
            BookingRequest.Status.DRAFT,
        )

        self.assertEqual(
            EmployeeBookingReservation.objects.filter(
                employee_code="TEST002",
                booking_date=self.booking_date,
            ).count(),
            1,
        )

    def test_booking_same_employee_next_day(self):

        request_1 = self.create_request(
            self.division_a,
            "TEST003",
        )

        request_2 = self.create_request(
            self.division_c,
            "TEST003",
            self.booking_date + timedelta(days=1),
        )

        submit_booking_request(request_1.pk)

        result = submit_booking_request(request_2.pk)

        result.refresh_from_db()

        self.assertEqual(
            result.status,
            BookingRequest.Status.PENDING_REVIEW,
        )

        self.assertEqual(
            EmployeeBookingReservation.objects.filter(
                employee_code="TEST003",
            ).count(),
            2,
        )

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

        request.refresh_from_db()

        self.assertEqual(
            request.status,
            BookingRequest.Status.DRAFT,
        )
