import os
from celery import Celery

_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_MONGO_BROKER = os.getenv('CELERY_BROKER_URL', 'mongodb://localhost:27017/omni-agent-queue')
_MONGO_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'mongodb://localhost:27017/omni-agent-queue')

# Prefer Redis when available — lower latency, better visibility, horizontal scale.
# Fall back to MongoDB so existing single-instance deployments keep working.
CELERY_BROKER_URL = _REDIS_URL or _MONGO_BROKER
CELERY_RESULT_BACKEND = _REDIS_URL or _MONGO_BACKEND

celery_app = Celery(
    'omni_agent',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['tasks'],
)

_extra: dict = {}
if not _REDIS_URL:
    _extra["mongodb_backend_settings"] = {
        "database": "omni-agent-queue",
        "taskmeta_collection": "celery_taskmeta",
    }

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    beat_schedule={
        'daily-patch-scan': {
            'task': 'tasks.run_periodic_patch_scan',
            'schedule': 86400.0,
        },
    },
    **_extra,
)

if __name__ == '__main__':
    celery_app.start()
