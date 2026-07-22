from pydantic import BaseModel

class Settings(BaseModel):
    # System settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # AI settings
    YOLO_MODEL: str = "yolov8n.pt"
    CONFIDENCE_THRESHOLD: float = 0.3
    
    # Traffic configuration
    CYCLE_TIME: int = 120 # total seconds
    MIN_GREEN_TIME: int = 12 # seconds
    
    # Web stream
    VIDEO_SOURCE: str = "test_video.mp4" # Default fallback video, can be an RTSP URL or 0 for webcam.

settings = Settings()
