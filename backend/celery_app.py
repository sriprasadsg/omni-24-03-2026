import os
from celery import Celery

# Configure Celery to use MongoDB
# Broker URL format: mongodb://userid:password@hostname:port/database_name
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'mongodb://localhost:27017/omni-agent-queue')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'mongodb://localhost:27017/omni-agent-queue')

celery_app = Celery(
    'omni_agent',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['tasks']  # This will look for tasks.py in the same module
)

# Optional configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # MongoDB specific settings
    mongodb_backend_settings={
        'database': 'omni-agent-queue',
        'taskmeta_collection': 'celery_taskmeta',
    },
    # Periodic Tasks
    beat_schedule={
        'daily-patch-scan': {
            'task': 'tasks.run_periodic_patch_scan',
            'schedule': 86400.0, # Every 24 hours
        },
    }
)

if __name__ == '__main__':
    celery_app.start()
