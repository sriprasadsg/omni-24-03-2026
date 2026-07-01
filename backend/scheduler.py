"""
Deployment Scheduler
Processes scheduled deployments automatically at their designated times
"""
import asyncio
import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from database import get_database

logger = logging.getLogger(__name__)

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
        
        logger.info("[Scheduler] Checking for scheduled deployments at %s", now.isoformat())
        
        # Find patch deployment jobs ready to execute
        patch_jobs = await db.patch_deployment_jobs.find({
            "status": "Scheduled",
            "scheduledAt": {"$lte": now.isoformat()}
        }).to_list(length=100)
        
        for job in patch_jobs:
            logger.info("[Scheduler] Executing scheduled patch deployment: %s", job["id"])
            
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
            logger.info("[Scheduler] Executing scheduled software deployment: %s", job["id"])
            
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
            logger.info("[Scheduler] Started %d scheduled deployments", total_executed)
        
    except Exception as e:
        logger.error("[Scheduler] Error processing scheduled deployments: %s", e)


async def process_pentest_schedules():
    """Trigger any pentest recurring scans that are due to run."""
    try:
        from pentest_integration_service import get_pentest_service
        db = get_database()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        cursor = db.pentest_schedules.find({"enabled": True})
        async for schedule in cursor:
            next_run = schedule.get("next_run")
            # Run if never run yet, or next_run has passed
            if next_run and next_run > now_iso:
                continue

            schedule_id = schedule["_id"]
            try:
                service = get_pentest_service(db)
                job = await service.create_scan_job(
                    target=schedule["target"],
                    scan_type=schedule["scan_type"],
                    tenant_id=schedule.get("tenant_id", ""),
                    created_by=f"scheduler:{schedule.get('created_by', 'system')}",
                )
                asyncio.create_task(service.execute_scan(job["id"]))

                # Calculate next_run from cron expression
                try:
                    trigger = CronTrigger.from_crontab(schedule["schedule"])
                    next_fire = trigger.get_next_fire_time(None, now)
                    next_run_iso = next_fire.isoformat() if next_fire else None
                except Exception:
                    next_run_iso = None

                await db.pentest_schedules.update_one(
                    {"_id": schedule_id},
                    {"$set": {"last_run": now_iso, "next_run": next_run_iso}},
                )
                logger.info("[PentestScheduler] Triggered scan for target %s (job %s)", schedule["target"], job["id"])
            except Exception as exc:
                logger.warning("[PentestScheduler] Failed to trigger scan for schedule %s: %s", schedule_id, exc)
    except Exception as exc:
        logger.error("[PentestScheduler] Error processing pentest schedules: %s", exc)


def start_scheduler():
    """Initialize and start the deployment scheduler"""
    global scheduler

    if scheduler is not None:
        logger.info("[Scheduler] Scheduler already running")
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

    # Add job to check for due pentest recurring scans every minute
    scheduler.add_job(
        process_pentest_schedules,
        trigger=IntervalTrigger(minutes=1),
        id='process_pentest_schedules',
        name='Process Pentest Schedules',
        replace_existing=True
    )

    scheduler.start()
    logger.info("[Scheduler] Scheduler started - deployment + pentest schedule checks every minute")


def stop_scheduler():
    """Stop the scheduler gracefully"""
    global scheduler
    
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("[Scheduler] Scheduler stopped")
