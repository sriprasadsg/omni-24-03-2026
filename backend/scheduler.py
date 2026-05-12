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
    """
    UI progress animation for patch deployment.
    Only animates progress — never overwrites status when real agents have been dispatched.
    Real completion is set by deployment_result_endpoints when agents report back.
    Falls back to marking Completed only when instructionsQueued == 0 (no real agents).
    """
    db = get_database()

    try:
        # Determine whether real agent instructions were queued
        job = await db.patch_deployment_jobs.find_one({"id": job_id}, {"instructionsQueued": 1})
        has_real_agents = job and job.get("instructionsQueued", 0) > 0

        total_operations = patch_count * asset_count

        for asset_idx in range(asset_count):
            for patch_idx in range(patch_count):
                await asyncio.sleep(2)

                # Stop animation if agents already completed/failed the job
                current = await db.patch_deployment_jobs.find_one(
                    {"id": job_id}, {"status": 1}
                )
                if current and current.get("status") in ("Completed", "Failed", "Partially Completed"):
                    return

                completed = (asset_idx * patch_count) + (patch_idx + 1)
                progress = int((completed / total_operations) * 99)  # cap at 99 — agents set 100

                await db.patch_deployment_jobs.update_one(
                    {"id": job_id},
                    {
                        "$set": {"progress": progress},
                        "$push": {"statusLog": {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "message": f"Waiting for agent: patch {patch_idx + 1}/{patch_count} on asset {asset_idx + 1}/{asset_count}",
                            "level": "info",
                        }},
                    },
                )

        # Only auto-complete when no real agents were dispatched (demo/no-agent mode)
        if not has_real_agents:
            await db.patch_deployment_jobs.update_one(
                {"id": job_id},
                {
                    "$set": {
                        "status": "Completed",
                        "progress": 100,
                        "completedAt": datetime.now(timezone.utc).isoformat(),
                    },
                    "$push": {"statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"[Demo] {patch_count} patches deployed to {asset_count} assets (no agents registered)",
                        "level": "warn",
                    }},
                },
            )

    except Exception as e:
        await db.patch_deployment_jobs.update_one(
            {"id": job_id},
            {
                "$set": {"status": "Failed", "error": str(e)},
                "$push": {"statusLog": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": f"Deployment failed: {e}",
                    "level": "error",
                }},
            },
        )


async def simulate_software_deployment(job_id: str, update_count: int):
    """
    Dispatches software update instructions to target agents and tracks real progress.
    Only auto-completes when no real agents were dispatched (demo/no-agent mode).
    """
    db = get_database()

    try:
        # Determine whether real agent instructions were queued
        job = await db.software_deployment_jobs.find_one({"id": job_id})
        has_real_agents = job and job.get("instructionsQueued", 0) > 0

        total = max(update_count, 1)

        for i in range(1, total + 1):
            await asyncio.sleep(2)

            # Stop animation if agents already completed/failed the job
            current = await db.software_deployment_jobs.find_one({"id": job_id}, {"status": 1})
            if current and current.get("status") in ("Completed", "Failed", "Partially Completed"):
                return

            progress = int((i / total) * 99)  # cap at 99 — agents set 100

            await db.software_deployment_jobs.update_one(
                {"id": job_id},
                {
                    "$set": {"progress": progress},
                    "$push": {"statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"Waiting for agent: update {i}/{total}",
                        "level": "info",
                    }},
                }
            )

        # Only auto-complete when no real agents were dispatched
        if not has_real_agents:
            await db.software_deployment_jobs.update_one(
                {"id": job_id},
                {
                    "$set": {
                        "status": "Completed",
                        "progress": 100,
                        "completedAt": datetime.now(timezone.utc).isoformat(),
                    },
                    "$push": {"statusLog": {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": f"[Demo] {total} software updates marked complete (no agents registered)",
                        "level": "warn",
                    }},
                }
            )

    except Exception as e:
        await db.software_deployment_jobs.update_one(
            {"id": job_id},
            {
                "$set": {"status": "Failed", "error": str(e)},
                "$push": {"statusLog": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": f"Deployment failed: {e}",
                    "level": "error",
                }},
            }
        )


async def process_scheduled_deployments():
    """
    Check for scheduled deployments and execute them
    Runs every minute via scheduler
    """
    try:
        from tenant_context import set_tenant_id
        set_tenant_id("platform-admin")
        
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
