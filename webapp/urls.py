from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView # 1. นำเข้า RedirectView
import django.urls

# --- เริ่ม Patch: ดักจับเพื่อแก้ปัญหา Django Ninja บน Django 6.1 ---
original_register_converter = django.urls.register_converter
def safe_register_converter(converter, type_name):
    if type_name == 'uuid':
        return 
    original_register_converter(converter, type_name)
django.urls.register_converter = safe_register_converter
# --- จบ Patch ---

from bookings.api import api  

urlpatterns = [
    path('', RedirectView.as_view(url='/api/docs', permanent=False)), # 2. สั่ง Redirect หน้าแรก
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]