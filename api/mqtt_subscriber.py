import asyncio
import json
import logging
from datetime import datetime

import aiomqtt
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal
from models import Detection

log = logging.getLogger(__name__)

# Shared in-process queue — the FastAPI WebSocket endpoint drains this
live_queue: asyncio.Queue = asyncio.Queue(maxsize=500)


async def _persist_detections(payload: dict) -> None:
    timestamp = datetime.fromisoformat(payload["timestamp"])
    async with AsyncSessionLocal() as session:
        for det in payload.get("detections", []):
            # Skip duplicate events (idempotent re-delivery)
            existing = await session.scalar(
                select(Detection.id).where(Detection.event_id == payload["event_id"])
            )
            if existing:
                continue

            session.add(Detection(
                event_id=payload["event_id"],
                frame_id=payload["frame_id"],
                line_id=payload.get("line_id", "unknown"),
                timestamp=timestamp,
                class_name=det["class_name"],
                confidence=det["confidence"],
                bbox=det["bbox"],
            ))
        await session.commit()


async def mqtt_listener() -> None:
    """Long-running task: subscribe to MQTT and fan out to DB + WebSocket queue."""
    log.info("Starting MQTT listener on %s:%s", settings.mqtt_broker, settings.mqtt_port)
    while True:
        try:
            async with aiomqtt.Client(settings.mqtt_broker, settings.mqtt_port) as client:
                await client.subscribe(settings.mqtt_topic)
                log.info("Subscribed to topic: %s", settings.mqtt_topic)
                async for message in client.messages:
                    try:
                        payload = json.loads(message.payload)
                        await _persist_detections(payload)
                        # Non-blocking put; drop if queue is full to avoid backpressure
                        try:
                            live_queue.put_nowait(payload)
                        except asyncio.QueueFull:
                            pass
                    except Exception as exc:
                        log.exception("Error processing MQTT message: %s", exc)
        except Exception as exc:
            log.warning("MQTT connection lost (%s), reconnecting in 5s…", exc)
            await asyncio.sleep(5)
