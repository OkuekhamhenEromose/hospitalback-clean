# api/celery.py
import os
from celery import Celery
from celery.schedules import crontab
from kombu import Queue, Exchange

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')

app = Celery('api')

# Use Redis with connection pooling
app.conf.broker_pool_limit = 10
app.conf.broker_connection_retry = True
app.conf.broker_connection_retry_on_startup = True
app.conf.broker_connection_max_retries = 100

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Configure queues
app.conf.task_queues = (
    Queue('default', Exchange('default'), routing_key='default'),
    Queue('high_priority', Exchange('high_priority'), routing_key='high_priority'),
    Queue('low_priority', Exchange('low_priority'), routing_key='low_priority'),
)

app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'default'
app.conf.task_default_routing_key = 'default'

app.conf.task_routes = {
    'hospital.tasks.process_blog_images': {'queue': 'low_priority'},
    'hospital.tasks.warm_cache': {'queue': 'low_priority'},
}

# Scheduled tasks for cache warming
app.conf.beat_schedule = {
    'warm-cache-every-hour': {
        'task': 'hospital.tasks.warm_cache',
        'schedule': crontab(minute=0),
        'options': {'queue': 'low_priority'},
    },
    'cleanup-cache-daily': {
        'task': 'hospital.tasks.cleanup_expired_cache',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
        'options': {'queue': 'low_priority'},
    },
}