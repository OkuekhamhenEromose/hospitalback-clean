# api/wsgi.py
import os

# EARLY PATCH - Must be first
import api.early_init  # This patches default_storage BEFORE Django loads

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')

application = get_wsgi_application()