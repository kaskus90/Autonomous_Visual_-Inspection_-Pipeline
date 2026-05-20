from datetime import datetime

from pydantic import BaseModel


class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class DetectionOut(BaseModel):
    id: int
    event_id: str
    frame_id: str
    line_id: str
    timestamp: datetime
    class_name: str
    confidence: float
    bbox: BBox

    model_config = {"from_attributes": True}


class DetectionStats(BaseModel):
    line_id: str
    total_detections: int
    defects_last_minute: int
    top_classes: list[dict]


class AlertConfigIn(BaseModel):
    defect_rate_threshold: int
    window_seconds: int = 60


class AlertConfigOut(AlertConfigIn):
    line_id: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertLogOut(BaseModel):
    id: int
    line_id: str
    defect_count: int
    threshold: int
    fired_at: datetime

    model_config = {"from_attributes": True}
