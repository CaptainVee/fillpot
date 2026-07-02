web: uvicorn fillpot.asgi:application --host 0.0.0.0 --port $PORT
worker: celery -A fillpot worker -l info
beat: celery -A fillpot beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
