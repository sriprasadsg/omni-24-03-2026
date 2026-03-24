import os
import redis
import json
from celery import Celery

# Initialize Redis connection
# Assuming generic default for now, similar to app.py
REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

def get_db_connection():
    return redis.from_url(REDIS_URL)

def list_recent_jobs(limit=50):
    """
    List recent Celery tasks by querying Redis for task metadata keys.
    Celery default result keys are 'celery-task-meta-<uuid>'
    """
    try:
        r = get_db_connection()
        # Scan for keys matches celery task meta
        # Note: keys() is expensive in prod, scan_iter is better but for <1000 keys keys() is fine for this demo
        keys = r.keys("celery-task-meta-*")
        
        jobs = []
        # Sort keys to get most recent if possible? Keys are UUIDs so order is random.
        # We'll fetch all and sort by date_done inside payload
        
        # We limit to last 'limit' keys to avoid overload if many
        for key in keys[:limit]: 
            data = r.get(key)
            if data:
                task_meta = json.loads(data)
                # Structure: {'status': 'SUCCESS', 'result': ..., 'traceback': ..., 'children': [], 'date_done': ..., 'task_id': ...}
                job = {
                    "task_id": task_meta.get("task_id"),
                    "status": task_meta.get("status"),
                    "date_done": task_meta.get("date_done"),
                    "result": str(task_meta.get("result")), # stringify for safety
                    "traceback": task_meta.get("traceback")
                }
                jobs.append(job)
        
        # Sort by date_done descending (newest first)
        # Handle None date_done (pending tasks might not have it?)
        jobs.sort(key=lambda x: x.get("date_done") or "", reverse=True)
        
        return jobs
    except Exception as e:
        print(f"Error listing jobs: {e}")
        return []

def get_job_details(task_id):
    try:
        r = get_db_connection()
        key = f"celery-task-meta-{task_id}"
        data = r.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"Error getting job details: {e}")
        return None
