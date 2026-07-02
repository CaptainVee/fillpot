import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fillpot.settings.local")

app = Celery("fillpot")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
