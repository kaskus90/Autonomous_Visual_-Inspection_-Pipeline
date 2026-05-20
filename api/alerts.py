import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select

from config import settings
from database import AsyncSessionLocal
from models import AlertConfig, AlertLog, Detection

log = logging.getLogger(__name__)

_last_alert: dict[str, datetime] = {}
_COOLDOWN_SECONDS = 60


async def _get_threshold(line_id: str) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        cfg = await session.scalar(
            select(AlertConfig).where(AlertConfig.line_id == line_id)
        )
    if cfg:
        return cfg.defect_rate_threshold, cfg.window_seconds
    return settings.alert_defect_rate_threshold, 60


async def _fire_alert(line_id: str, count: int, threshold: int) -> None:
    log.warning("ALERT: line=%s defects=%d threshold=%d", line_id, count, threshold)

    async with AsyncSessionLocal() as session:
        session.add(AlertLog(line_id=line_id, defect_count=count, threshold=threshold))
        await session.commit()

    if settings.alert_webhook_url:
        payload = {
            "text": f"[ALERT] Line `{line_id}`: {count} defects detected (threshold: {threshold})"
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(settings.alert_webhook_url, json=payload)
        except Exception as exc:
            log.error("Webhook delivery failed: %s", exc)


async def alert_worker() -> None:
    """Polls the DB every 30 seconds and fires alerts when thresholds are exceeded."""
    log.info("Alert worker started")
    while True:
        await asyncio.sleep(30)
        try:
            threshold, window = await _get_threshold("line1")
            since = datetime.now(timezone.utc) - timedelta(seconds=window)

            async with AsyncSessionLocal() as session:
                count = await session.scalar(
                    select(func.count(Detection.id)).where(Detection.timestamp >= since)
                )

            if count and count >= threshold:
                last = _last_alert.get("line1")
                if not last or (datetime.now(timezone.utc) - last).seconds >= _COOLDOWN_SECONDS:
                    _last_alert["line1"] = datetime.now(timezone.utc)
                    await _fire_alert("line1", count, threshold)
        except Exception as exc:
            log.exception("Alert worker error: %s", exc)
