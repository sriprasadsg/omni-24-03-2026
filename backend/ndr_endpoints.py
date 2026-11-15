"""Network detection routes (88.1, stage 1): the sensor summary, and nothing else yet.

The earlier routes (anomalies, manual flow ingest, on-demand detection and the demo seeder) served rows that no
real sensor produced, and the summary reported ``detection_running: True`` whatever was connected. They are gone.
What is left answers one question from real records: which network sensors does this tenant have, and what state
is each in. With no sensor the answer is an empty list. Sensor ingest and the alert lists arrive with stage 3.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

import ndr_sensors
from auth_utils import require_auth
from database import get_db

router = APIRouter(prefix="/api/ndr", tags=["network-detection-response"])


@router.get("/summary")
async def get_summary(user=Depends(require_auth), db=Depends(get_db)):
    """The caller's tenant's network sensors, each with its state from ``ndr_sensors.sensor_health``."""
    now = datetime.now(timezone.utc)
    sensors = []
    for sensor, samples in await ndr_sensors.sensors_with_samples(db, ndr_sensors.HEALTH_SAMPLES):
        health = ndr_sensors.sensor_health(sensor, samples, now)
        sensors.append({"sensorId": sensor.get("sensorId"), "name": sensor.get("name"),
                        "state": health["state"], "reason": health["reason"],
                        "lastStatsAt": health["lastStatsAt"], "retiredAt": sensor.get("retiredAt")})
    return {"sensors": sensors}
