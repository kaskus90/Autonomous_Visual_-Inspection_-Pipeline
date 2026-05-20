import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from ultralytics import YOLO

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [inference] %(message)s")
log = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "inspections/line1/detections")
VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "demo")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 0.4))
CAPTURE_FPS = int(os.getenv("CAPTURE_FPS", 5))
FRAMES_DIR = Path(os.getenv("FRAMES_DIR", "/frames"))

FRAMES_DIR.mkdir(parents=True, exist_ok=True)

DEFECT_CLASSES = ["scratch", "dent", "crack", "contamination", "discoloration"]


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log.info("Connected to MQTT broker %s:%s", MQTT_BROKER, MQTT_PORT)
        else:
            log.error("MQTT connect failed, reason code %s", reason_code)

    client.on_connect = on_connect

    for attempt in range(1, 11):
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_start()
            return client
        except Exception as exc:
            log.warning("MQTT attempt %d/10 failed: %s", attempt, exc)
            time.sleep(3)

    raise RuntimeError("Could not connect to MQTT broker after 10 attempts")


def make_synthetic_frame(frame_num: int) -> tuple[np.ndarray, list]:
    """Generate a fake conveyor-belt inspection frame with random defects."""
    frame = np.full((480, 640, 3), 45, dtype=np.uint8)

    # Belt surface
    cv2.rectangle(frame, (0, 180), (640, 300), (72, 64, 55), -1)
    # Belt edges
    cv2.rectangle(frame, (0, 175), (640, 185), (55, 48, 40), -1)
    cv2.rectangle(frame, (0, 295), (640, 305), (55, 48, 40), -1)
    # Belt texture lines
    for x in range(0, 640, 60):
        cv2.line(frame, (x, 180), (x, 300), (60, 52, 44), 1)

    # Product items on the belt
    for i in range(3):
        px = 80 + i * 200 + (frame_num * 3 % 60) - 30
        py = 215
        cv2.rectangle(frame, (px, py), (px + 80, py + 50), (140, 130, 120), -1)
        cv2.rectangle(frame, (px, py), (px + 80, py + 50), (100, 90, 80), 2)

    detections = []
    # ~35% chance of a defect per frame
    if random.random() < 0.35:
        num_defects = random.randint(1, 2)
        for _ in range(num_defects):
            x1 = random.randint(40, 540)
            y1 = random.randint(190, 260)
            x2 = x1 + random.randint(18, 55)
            y2 = y1 + random.randint(12, 35)
            defect_color = random.choice([
                (30, 30, 220),   # red scratch
                (20, 200, 220),  # yellow dent
                (220, 60, 20),   # blue crack
                (180, 30, 180),  # purple contamination
            ])
            cv2.ellipse(
                frame,
                ((x1 + x2) // 2, (y1 + y2) // 2),
                ((x2 - x1) // 2, (y2 - y1) // 2),
                random.randint(0, 180), 0, 360,
                defect_color, -1,
            )
            class_name = random.choice(DEFECT_CLASSES)
            detections.append({
                "class_id": DEFECT_CLASSES.index(class_name),
                "class_name": class_name,
                "confidence": round(random.uniform(0.52, 0.97), 4),
                "bbox": {"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)},
            })

    # Overlay text
    cv2.putText(frame, f"LINE-1  DEMO  FRAME {frame_num:05d}", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    cv2.putText(frame, ts, (10, 460),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1)

    return frame, detections


def run_demo(client: mqtt.Client) -> None:
    log.info("Running in DEMO mode (synthetic frames, no camera needed)")
    frame_num = 0
    frame_interval = 1.0 / CAPTURE_FPS

    while True:
        start = time.monotonic()
        frame, detections = make_synthetic_frame(frame_num)

        if detections:
            timestamp = datetime.now(timezone.utc).isoformat()
            frame_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            frame_path = FRAMES_DIR / f"{frame_id}.jpg"

            # Draw bboxes onto the saved frame
            annotated = frame.copy()
            for d in detections:
                b = d["bbox"]
                cv2.rectangle(annotated, (b["x1"], b["y1"]), (b["x2"], b["y2"]), (0, 255, 0), 2)
                label = f"{d['class_name']} {d['confidence']:.2f}"
                cv2.putText(annotated, label, (b["x1"], b["y1"] - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            cv2.imwrite(str(frame_path), annotated)

            event = {
                "event_id": str(uuid.uuid4()),
                "frame_id": frame_id,
                "timestamp": timestamp,
                "line_id": "line1",
                "detections": detections,
            }
            client.publish(MQTT_TOPIC, json.dumps(event), qos=1)
            log.info("Published %d detection(s) — %s",
                     len(detections), ", ".join(d["class_name"] for d in detections))

        frame_num += 1
        elapsed = time.monotonic() - start
        sleep_for = max(0.0, frame_interval - elapsed)
        if sleep_for:
            time.sleep(sleep_for)


def run_camera(client: mqtt.Client, source: str) -> None:
    model = YOLO("yolov8n.pt")
    log.info("YOLOv8n model loaded")

    src = int(source) if source.isdigit() else source
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source: {source!r}")
    log.info("Opened video source: %s", source)

    is_file = not (isinstance(src, int))
    frame_interval = 1.0 / CAPTURE_FPS
    last_capture = 0.0

    try:
        while True:
            now = time.monotonic()
            if now - last_capture < frame_interval:
                time.sleep(0.005)
                continue
            last_capture = now

            ok, frame = cap.read()
            if not ok:
                if is_file:
                    log.info("End of video file, looping")
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                log.error("Failed to read frame, stopping")
                break

            timestamp = datetime.now(timezone.utc).isoformat()
            frame_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            results = model(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)[0]

            detections = []
            for box in results.boxes:
                detections.append({
                    "class_id": int(box.cls),
                    "class_name": model.names[int(box.cls)],
                    "confidence": round(float(box.conf), 4),
                    "bbox": {
                        "x1": round(float(box.xyxy[0][0])),
                        "y1": round(float(box.xyxy[0][1])),
                        "x2": round(float(box.xyxy[0][2])),
                        "y2": round(float(box.xyxy[0][3])),
                    },
                })

            if detections:
                frame_path = FRAMES_DIR / f"{frame_id}.jpg"
                cv2.imwrite(str(frame_path), results.plot())

                event = {
                    "event_id": str(uuid.uuid4()),
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "line_id": "line1",
                    "detections": detections,
                }
                client.publish(MQTT_TOPIC, json.dumps(event), qos=1)
                log.info("Published %d detection(s) for frame %s", len(detections), frame_id)
    finally:
        cap.release()


def run() -> None:
    client = connect_mqtt()
    try:
        if VIDEO_SOURCE.lower() == "demo":
            run_demo(client)
        else:
            run_camera(client, VIDEO_SOURCE)
    finally:
        client.loop_stop()
        client.disconnect()
        log.info("Inference service stopped")


if __name__ == "__main__":
    run()
