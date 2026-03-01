# api/wsgi.py
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')

application = get_wsgi_application()

# FORCE STORAGE INITIALIZATION
import django.core.files.storage as storage_module
from hospital.storage_backends import MediaStorage

print("[WSGI] Initializing default_storage...")
# Force initialization by accessing it
_ = storage_module.default_storage
print(f"[WSGI] default_storage: {storage_module.default_storage.__class__.__name__}")