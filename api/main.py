import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alerts import alert_worker
from database import Base, engine, get_db
from models import AlertConfig, AlertLog, Detection
from mqtt_subscriber import live_queue, mqtt_listener
from schemas import AlertConfigIn, AlertConfigOut, AlertLogOut, DetectionOut, DetectionStats

logging.basicConfig(level=logging.INFO, format="%(asctime)s [api] %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    tasks = [
        asyncio.create_task(mqtt_listener()),
        asyncio.create_task(alert_worker()),
    ]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Visual Inspection API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Detections
# ---------------------------------------------------------------------------

@app.get("/detections", response_model=list[DetectionOut])
async def list_detections(
    limit: int = 50,
    offset: int = 0,
    line_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Detection).order_by(desc(Detection.timestamp)).offset(offset).limit(limit)
    if line_id:
        q = q.where(Detection.line_id == line_id)
    result = await db.scalars(q)
    return result.all()


@app.get("/detections/stats", response_model=DetectionStats)
async def detection_stats(line_id: str = "line1", db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(minutes=1)

    total = await db.scalar(select(func.count(Detection.id)))
    last_minute = await db.scalar(
        select(func.count(Detection.id)).where(
            Detection.line_id == line_id, Detection.timestamp >= since
        )
    )
    top_rows = await db.execute(
        select(Detection.class_name, func.count(Detection.id).label("count"))
        .where(Detection.line_id == line_id)
        .group_by(Detection.class_name)
        .order_by(desc("count"))
        .limit(5)
    )
    top_classes = [{"class_name": r[0], "count": r[1]} for r in top_rows]

    return DetectionStats(
        line_id=line_id,
        total_detections=total or 0,
        defects_last_minute=last_minute or 0,
        top_classes=top_classes,
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@app.get("/alerts/config", response_model=AlertConfigOut)
async def get_alert_config(line_id: str = "line1", db: AsyncSession = Depends(get_db)):
    cfg = await db.scalar(select(AlertConfig).where(AlertConfig.line_id == line_id))
    if not cfg:
        cfg = AlertConfig(line_id=line_id, defect_rate_threshold=5, window_seconds=60)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


@app.post("/alerts/config", response_model=AlertConfigOut)
async def set_alert_config(
    body: AlertConfigIn, line_id: str = "line1", db: AsyncSession = Depends(get_db)
):
    cfg = await db.scalar(select(AlertConfig).where(AlertConfig.line_id == line_id))
    if cfg:
        cfg.defect_rate_threshold = body.defect_rate_threshold
        cfg.window_seconds = body.window_seconds
    else:
        cfg = AlertConfig(line_id=line_id, **body.model_dump())
        db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@app.get("/alerts/history", response_model=list[AlertLogOut])
async def alert_history(limit: int = 20, db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(
        select(AlertLog).order_by(desc(AlertLog.fired_at)).limit(limit)
    )
    return rows.all()


# ---------------------------------------------------------------------------
# Live WebSocket feed
# ---------------------------------------------------------------------------

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                event = await asyncio.wait_for(live_queue.get(), timeout=30)
                await websocket.send_text(json.dumps(event))
            except asyncio.TimeoutError:
                await websocket.send_text('{"type":"ping"}')
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}
