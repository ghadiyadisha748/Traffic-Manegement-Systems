import cv2
import time
import numpy as np
from ultralytics import YOLO
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

    def process_stream(self):
        # Fallback if video file doesn't exist: simulate frames
        cap = cv2.VideoCapture(settings.VIDEO_SOURCE)
        if not cap.isOpened():
            logger.warning(f"Could not open {settings.VIDEO_SOURCE}. Using simulated frames.")
            cap = None

        prev_time = time.time()
        
        while True:
            if cap:
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0) # Loop video
                    continue
            else:
                # Generate a dummy noise frame if no camera/video
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "NO VIDEO SOURCE", (150, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            # Inference
            curr_time = time.time()
            fps = 1.0 / (curr_time - prev_time + 0.001)
            prev_time = curr_time
            
            inf_start = time.time()
            detections = []
            
            if self.model and cap:
                results = self.model(frame, verbose=False, conf=settings.CONFIDENCE_THRESHOLD)[0]
                
                for box in results.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    cls_name = self.model.names[cls_id]
                    
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    detections.append({
                        "class_name": cls_name,
                        "confidence": conf,
                        "box": [x1, y1, x2, y2]
                    })
                    
                    # Draw box on frame
                    color = (0, 255, 0)
                    if cls_name in ['truck', 'bus']: color = (0, 165, 255) # Orange
                    if cls_name == 'person': color = (255, 0, 0) # Blue
                    
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, f"{cls_name} {conf:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            inference_time = (time.time() - inf_start) * 1000 # ms
            
            # Add telemetry to frame
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f"Inf: {inference_time:.1f}ms", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            frame_bytes = buffer.tobytes()
            
            yield frame_bytes, detections, fps, inference_time

engine = AIEngine()
