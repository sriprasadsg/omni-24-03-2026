#!/usr/bin/env python3
"""
ML Model Training Script
------------------------
Trains the Random Forest (patch failure prediction) and Isolation Forest
(anomaly detection) models and saves them to backend/models/.

Usage:
    cd backend
    python train_ml_models.py

The script tries real data from MongoDB first. If there isn't enough historical
data yet, it seeds with synthetic data so the ML path is active from day one.
"""
import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger("train_ml_models")

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
PATCH_MODEL_PATH = os.path.join(MODELS_DIR, "patch_model.joblib")
ANOMALY_MODEL_PATH = os.path.join(MODELS_DIR, "anomaly_model.joblib")


def _check_deps():
    try:
        import sklearn  # noqa: F401
        import joblib    # noqa: F401
        import numpy     # noqa: F401
    except ImportError as e:
        logger.error("Missing dependency: %s  →  pip install scikit-learn joblib numpy", e)
        sys.exit(1)


def _train_patch_model(X, y):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    import joblib

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    clf.fit(X_train, y_train)
    accuracy = clf.score(X_test, y_test)
    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(clf, PATCH_MODEL_PATH)
    return accuracy


def _train_anomaly_model(X):
    from sklearn.ensemble import IsolationForest
    import joblib

    iso = IsolationForest(contamination=0.1, random_state=42)
    iso.fit(X)
    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(iso, ANOMALY_MODEL_PATH)


def _seed_patch_data():
    """Generate synthetic patch deployment training data."""
    import numpy as np
    from sklearn.datasets import make_classification

    logger.info("Generating synthetic patch deployment data (800 samples)…")
    X, y = make_classification(
        n_samples=800, n_features=8, n_informative=6, n_redundant=1,
        weights=[0.8, 0.2], random_state=42,
    )
    return X, y


def _seed_anomaly_data():
    """Generate synthetic daily deployment stats for anomaly detection."""
    import numpy as np

    logger.info("Generating synthetic anomaly detection data (90 days)…")
    rng = np.random.default_rng(42)
    # 80 normal days + 10 anomalous days
    normal = np.column_stack([
        rng.integers(1, 15, 80),
        rng.uniform(0.0, 0.1, 80),
    ])
    anomalous = np.column_stack([
        rng.integers(30, 60, 10),
        rng.uniform(0.4, 1.0, 10),
    ])
    return np.vstack([normal, anomalous])


async def _load_real_patch_data():
    """Try to load real patch deployment data from MongoDB."""
    try:
        from database import get_database
        db = get_database()
        if db is None:
            return None, None

        deployments = await db.patch_deployment_jobs.find(
            {"status": {"$in": ["completed", "failed"]}}, {"_id": 0}
        ).to_list(length=10000)

        if len(deployments) < 50:
            logger.info("Only %d deployment records found; using synthetic seed data.", len(deployments))
            return None, None

        import numpy as np
        X, y = [], []
        for dep in deployments:
            sev = {"Critical": 1.0, "High": 0.75, "Medium": 0.5, "Low": 0.25}
            for patch_id in dep.get("patch_ids", []):
                patch = await db.patches.find_one({"id": patch_id}, {"_id": 0}) or {}
                # Resolve asset features from MongoDB
                asset_id = (dep.get("asset_ids") or [None])[0]
                asset = {}
                if asset_id:
                    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0}) or {}

                from datetime import datetime, timezone
                created_at_str = asset.get("createdAt", "")
                try:
                    created_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    os_age = (datetime.now(timezone.utc) - created_dt).days
                except Exception:
                    os_age = 365

                uptime = asset.get("uptime_hours") or 72

                if asset_id:
                    total_deps = await db.patch_deployment_jobs.count_documents({"asset_ids": asset_id})
                    success_deps = await db.patch_deployment_jobs.count_documents(
                        {"asset_ids": asset_id, "status": "completed"}
                    )
                    historical_success_rate = (success_deps / total_deps) if total_deps > 0 else 0.8
                else:
                    historical_success_rate = 0.8

                X.append([
                    sev.get(patch.get("severity"), 0.5),
                    (patch.get("cvss_score") or 0) / 10.0,
                    os_age,
                    uptime,
                    historical_success_rate,
                    len(deployments),
                    patch.get("size_mb") or 10,
                    1 if patch.get("requiresReboot") else 0,
                ])
                y.append(1 if dep["status"] == "failed" else 0)

        if len(X) < 10:
            return None, None

        logger.info("Loaded %d real patch deployment records.", len(X))
        return np.array(X), np.array(y)

    except Exception as e:
        logger.warning("Could not load MongoDB data (%s); using synthetic seed data.", e)
        return None, None


async def _load_real_anomaly_data():
    """Try to load real daily deployment stats from MongoDB."""
    try:
        from database import get_database
        import numpy as np
        from collections import defaultdict

        db = get_database()
        if db is None:
            return None

        deployments = await db.patch_deployment_jobs.find(
            {"status": {"$in": ["completed", "failed"]}}, {"_id": 0}
        ).to_list(length=10000)

        if len(deployments) < 20:
            return None

        daily = defaultdict(lambda: {"total": 0, "failed": 0})
        for dep in deployments:
            day = (dep.get("created_at") or "")[:10]
            if not day:
                continue
            daily[day]["total"] += 1
            if dep.get("status") == "failed":
                daily[day]["failed"] += 1

        X = [
            [s["total"], s["failed"] / s["total"] if s["total"] > 0 else 0]
            for s in daily.values()
        ]
        if len(X) < 5:
            return None

        logger.info("Loaded %d days of real deployment stats for anomaly detection.", len(X))
        return np.array(X)

    except Exception as e:
        logger.warning("Could not load MongoDB anomaly data (%s); using synthetic seed data.", e)
        return None


async def main():
    _check_deps()
    import numpy as np

    logger.info("=" * 55)
    logger.info("OmniAgent ML Model Training")
    logger.info("Output directory: %s", MODELS_DIR)
    logger.info("=" * 55)

    # ── Patch failure model ───────────────────────────────────────
    logger.info("\n[1/2] Training patch failure prediction model…")
    X, y = await _load_real_patch_data()
    if X is None:
        X, y = _seed_patch_data()

    accuracy = _train_patch_model(X, y)
    logger.info("  Random Forest trained — accuracy: %.1f%%", accuracy * 100)
    logger.info("  Saved to: %s", PATCH_MODEL_PATH)

    # ── Anomaly detection model ───────────────────────────────────
    logger.info("\n[2/2] Training deployment anomaly detection model…")
    X_a = await _load_real_anomaly_data()
    if X_a is None:
        X_a = _seed_anomaly_data()

    _train_anomaly_model(X_a)
    logger.info("  Isolation Forest trained — %d samples", len(X_a))
    logger.info("  Saved to: %s", ANOMALY_MODEL_PATH)

    logger.info("\n✓ Training complete. Restart the backend to load the new models.")


if __name__ == "__main__":
    asyncio.run(main())
