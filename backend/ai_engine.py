import cv2
import time
import numpy as np
from ultralytics import YOLO
from shapely.geometry import Point, Polygon
from config import settings
import logging

logger = logging.getLogger(__name__)

class AIEngine:
    def __init__(self):
        try:
            self.model = YOLO(settings.YOLO_MODEL)
            logger.info(f"Loaded YOLO model: {settings.YOLO_MODEL}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.model = None

        # Configurable ROIs for a standard 640x480 traffic feed
        self.rois = {
            "Road A": Polygon([(250, 0), (390, 0), (390, 150), (250, 150)]), # North
            "Road B": Polygon([(490, 150), (640, 150), (640, 330), (490, 330)]), # East
            "Road C": Polygon([(250, 330), (390, 330), (390, 480), (250, 480)]), # South
            "Road D": Polygon([(0, 150), (150, 150), (150, 330), (0, 330)]), # West
            "Pedestrian Crossing": Polygon([(150, 150), (490, 150), (490, 330), (150, 330)]) # Center
        }
        
    def get_lane(self, center_x, center_y):
        pt = Point(center_x, center_y)
        for name, poly in self.rois.items():
            if poly.contains(pt):
                return name
        return "Unknown"

    def process_stream(self):
        cap = cv2.VideoCapture(settings.VIDEO_SOURCE)
        if not cap.isOpened():
            logger.warning(f"Could not open {settings.VIDEO_SOURCE}. Simulated frames used.")
            cap = None

        prev_time = time.time()
        
        while True:
            if cap:
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                frame = cv2.resize(frame, (640, 480))
            else:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "NO VIDEO SOURCE", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            curr_time = time.time()
            fps = 1.0 / (curr_time - prev_time + 0.001)
            prev_time = curr_time
            
            inf_start = time.time()
            detections = []
            
            # Draw ROIs
            for name, poly in self.rois.items():
                pts = np.array(poly.exterior.coords, np.int32)
                pts = pts.reshape((-1, 1, 2))
                color = (255, 0, 0) if "Pedestrian" in name else (0, 255, 255)
                cv2.polylines(frame, [pts], True, color, 1)

            if self.model and cap:
                # ByteTrack Integration
                results = self.model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False, conf=settings.CONFIDENCE_THRESHOLD)[0]
                
                if results.boxes is not None and results.boxes.id is not None:
                    boxes = results.boxes.xyxy.cpu().numpy()
                    track_ids = results.boxes.id.int().cpu().tolist()
                    clss = results.boxes.cls.cpu().tolist()
                    confs = results.boxes.conf.cpu().tolist()
                    
                    for box, track_id, cls_id, conf in zip(boxes, track_ids, clss, confs):
                        cls_name = self.model.names[int(cls_id)]
                        x1, y1, x2, y2 = map(int, box)
                        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                        
                        lane = self.get_lane(cx, cy)
                        
                        detections.append({
                            "track_id": track_id,
                            "class_name": cls_name,
                            "confidence": float(conf),
                            "box": [x1, y1, x2, y2],
                            "center": [cx, cy],
                            "lane": lane
                        })
                        
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, f"ID:{track_id} {cls_name} ({lane})", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
                        cv2.circle(frame, (cx, cy), 3, (0, 0, 255), -1)
            
            inference_time = (time.time() - inf_start) * 1000
            
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"Inf: {inference_time:.1f}ms", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            yield buffer.tobytes(), detections, fps, inference_time

engine = AIEngine()
