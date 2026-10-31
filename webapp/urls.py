from django.contrib import admin
from django.urls import path
from bookings.api import api  # นำเข้าตัวแปร api ที่เราเพิ่งสร้าง

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),       # เชื่อมต่อ API ทั้งหมดเข้าที่ /api/
]