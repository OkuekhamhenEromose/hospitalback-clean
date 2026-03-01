# api/early_init.py
"""
Must be imported BEFORE any other Django imports.
Patches default_storage to use correct class.
"""
import os
import sys

# Skip patching during management commands
MANAGEMENT_COMMANDS = ['makemigrations', 'migrate', 'collectstatic']
if any(cmd in sys.argv for cmd in MANAGEMENT_COMMANDS):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
    print(f"[EARLY INIT] Skipped during management command")
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
    
    try:
        import django.core.files.storage as storage_module
        from django.conf import settings
        from decouple import config
        
        # Check if AWS credentials are actually provided and non-empty
        AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
        AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
        AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
        
        # Only patch if ALL credentials are provided AND not empty
        if (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY 
            and AWS_STORAGE_BUCKET_NAME):
            try:
                from hospital.storage_backends import MediaStorage
                storage_module.default_storage = MediaStorage()
                print(f"[EARLY INIT] Patched default_storage to: MediaStorage")
            except Exception as e:
                print(f"[EARLY INIT] Failed to patch storage: {e}")
        else:
            print(f"[EARLY INIT] Using default storage (AWS credentials not provided)")
            
    except Exception as e:
        print(f"[EARLY INIT] Warning: Could not configure storage: {e}")