import os
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

CELERY_TASK_QUEUES = (
    Queue('high_priority'),
    Queue('default'),
    Queue('low_priority'),
)

CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_DEFAULT_EXCHANGE = 'default'
CELERY_TASK_DEFAULT_ROUTING_KEY = 'default'



os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ussd_settings.settings')

app = Celery('ussd_settings')

app.conf.beat_scheduler = 'django_celery_beat.schedulers:DatabaseScheduler'

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()


app.conf.beat_schedule = {
    'daily-quiz-reminders': {
        'task': 'whatsapp_ussd.tasks.send_daily_reminders',
        'schedule': crontab(hour=8, minute=0),  # 8:00 AM
    },
    'check-expiring-subscriptions': {
        'task': 'whatsapp_ussd.tasks.check_expiring_subscriptions',
        'schedule': crontab(hour=10, minute=0),  # 10:00 AM
    },
    'cleanup-expired-sessions': {
        'task': 'whatsapp_ussd.tasks.cleanup_expired_sessions',
        'schedule': crontab(hour=2, minute=0),  # 2:00 AM
    },
}