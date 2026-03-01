# api/celery.py
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')

app = Celery('api')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Scheduled tasks for cache warming
app.conf.beat_schedule = {
    'warm-cache-every-hour': {
        'task': 'hospital.tasks.warm_cache',
        'schedule': crontab(minute=0),  # Every hour
    },
}