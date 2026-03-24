"""
Deployment Scheduler
Processes scheduled deployments automatically at their designated times
"""
import asyncio
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from database import get_database
import uuid

# Global scheduler instance
scheduler = None

async def simulate_patch_deployment(job_id: str, patch_count: int, asset_count: int):
    """Simulate patch deployment progress (imported from app.py logic)"""
    db = get_database()
    
    try:
        total_operations = patch_count * asset_count
        
        for asset_idx in range(asset_count):
            for patch_idx in range(patch_count):
                await asyncio.sleep(2)  # Simulate deployment time
                
                completed = (asset_idx * patch_count) + (patch_idx + 1)
                progress = int((completed / total_operations) * 100)
                
                log_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": f"Deployed patch {patch_idx + 1}/{patch_count} to asset {asset_idx + 1}/{asset_count}"
                }
                
                await db.patch_deployment_jobs.update_one(
                    {"id": job_id},
                    {
                        "$set": {"progress": progress},
                        "$push": {"statusLog": log_entry}
                    }
                )
        
        # Mark as completed
        await db.patch_deployment_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "Completed",
                    "progress": 100,
                    "completedAt": datetime.now(timezone.utc).isoformat()
                },
                "$push": {
                    "statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"All {patch_count} patches successfully deployed to {asset_count} assets"
                    }
                }
            }
        )
        
    except Exception as e:
        # Mark as failed
        await db.patch_deployment_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "Failed",
                    "error": str(e)
                },
                "$push": {
                    "statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"Deployment failed: {str(e)}",
                        "level": "error"
                    }
                }
            }
        )


async def simulate_software_deployment(job_id: str, update_count: int):
    """Simulate software update deployment progress"""
    db = get_database()
    
    try:
        for i in range(1, update_count + 1):
            await asyncio.sleep(3)  # Simulate deployment time
            
            progress = int((i / update_count) * 100)
            
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": f"Deployed {i}/{update_count} software update(s)"
            }
            
            await db.software_deployment_jobs.update_one(
                {"id": job_id},
                {
                    "$set": {"progress": progress},
                    "$push": {"statusLog": log_entry}
                }
            )
        
        # Mark as completed
        await db.software_deployment_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "Completed",
                    "progress": 100,
                    "completedAt": datetime.now(timezone.utc).isoformat()
                },
                "$push": {
                    "statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"All {update_count} software updates successfully deployed"
                    }
                }
            }
        )
        
    except Exception as e:
        # Mark as failed
        await db.software_deployment_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "Failed",
                    "error": str(e)
                },
                "$push": {
                    "statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"Deployment failed: {str(e)}",
                        "level": "error"
                    }
                }
            }
        )


async def process_scheduled_deployments():
    """
    Check for scheduled deployments and execute them
    Runs every minute via scheduler
    """
    try:
        db = get_database()
        now = datetime.now(timezone.utc)
        
        print(f"[Scheduler] Checking for scheduled deployments at {now.isoformat()}")
        
        # Find patch deployment jobs ready to execute
        patch_jobs = await db.patch_deployment_jobs.find({
            "status": "Scheduled",
            "scheduledAt": {"$lte": now.isoformat()}
        }).to_list(length=100)
        
        for job in patch_jobs:
            print(f"[Scheduler] Executing scheduled patch deployment: {job['id']}")
            
            # Update status to In Progress
            await db.patch_deployment_jobs.update_one(
                {"id": job["id"]},
                {
                    "$set": {
                        "status": "In Progress",
                        "startedAt": now.isoformat()
                    },
                    "$push": {
                        "statusLog": {
                            "timestamp": now.isoformat(),
                            "message": "Scheduled deployment started automatically"
                        }
                    }
                }
            )
            
            # Trigger deployment simulation
            patch_count = len(job.get("targetPatchIds", []))
            asset_count = len(job.get("targetAssetIds", []))
            asyncio.create_task(simulate_patch_deployment(job["id"], patch_count, asset_count))
        
        # Find software deployment jobs ready to execute
        software_jobs = await db.software_deployment_jobs.find({
            "status": "Scheduled",
            "scheduledAt": {"$lte": now.isoformat()}
        }).to_list(length=100)
        
        for job in software_jobs:
            print(f"[Scheduler] Executing scheduled software deployment: {job['id']}")
            
            # Update status to In Progress
            await db.software_deployment_jobs.update_one(
                {"id": job["id"]},
                {
                    "$set": {
                        "status": "In Progress",
                        "startedAt": now.isoformat()
                    },
                    "$push": {
                        "statusLog": {
                            "timestamp": now.isoformat(),
                            "message": "Scheduled deployment started automatically"
                        }
                    }
                }
            )
            
            # Trigger deployment simulation
            update_count = len(job.get("softwareUpdates", []))
            asyncio.create_task(simulate_software_deployment(job["id"], update_count))
        
        total_executed = len(patch_jobs) + len(software_jobs)
        if total_executed > 0:
            print(f"[Scheduler] Started {total_executed} scheduled deployments")
        
    except Exception as e:
        print(f"[Scheduler] Error processing scheduled deployments: {e}")


def start_scheduler():
    """Initialize and start the deployment scheduler"""
    global scheduler
    
    if scheduler is not None:
        print("[Scheduler] Scheduler already running")
        return
    
    scheduler = AsyncIOScheduler()
    
    # Add job to check for scheduled deployments every minute
    scheduler.add_job(
        process_scheduled_deployments,
        trigger=IntervalTrigger(minutes=1),
        id='process_scheduled_deployments',
        name='Process Scheduled Deployments',
        replace_existing=True
    )
    
    scheduler.start()
    print("[Scheduler] Scheduler started - checking for scheduled deployments every minute")


def stop_scheduler():
    """Stop the scheduler gracefully"""
    global scheduler
    
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        print("[Scheduler] Scheduler stopped")
