import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn
import logging
import time

from ai_engine import engine
from traffic_logic import traffic_controller
from websocket_manager import manager
from database import get_db, engine as db_engine, Base
import db_models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables for Phase 1
Base.metadata.create_all(bind=db_engine)

app = FastAPI(title="Traffic Management AI Backend - Phase 1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_frame = None

async def ai_loop():
    global latest_frame
    logger.info("Starting AI tracking loop...")
    
    loop = asyncio.get_running_loop()
    generator = engine.process_stream()
    
    while True:
        try:
            # We will yield frame_bytes, tracked_detections, fps, inference_time
            frame_bytes, detections, fps, inference_time = await loop.run_in_executor(None, next, generator)
            latest_frame = frame_bytes
            
            # Save historical stats to DB periodically inside traffic_controller, or here.
            state_dict = traffic_controller.update(detections, fps, inference_time)
            
            await manager.broadcast_state(state_dict)
            
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error in AI loop: {e}")
            await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ai_loop())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def generate_mjpeg():
    global latest_frame
    while True:
        if latest_frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        time.sleep(0.05)

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

# --- REST APIs ---
@app.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    return {"status": "ok", "message": "Dashboard data"}

@app.get("/api/intersections")
def get_intersections(db: Session = Depends(get_db)):
    return db.query(db_models.Intersection).all()

@app.get("/api/history")
def get_history(db: Session = Depends(get_db)):
    return db.query(db_models.TrafficHistory).order_by(db_models.TrafficHistory.timestamp.desc()).limit(10).all()

@app.get("/api/system")
def get_system(db: Session = Depends(get_db)):
    return db.query(db_models.SystemHealthLog).order_by(db_models.SystemHealthLog.timestamp.desc()).limit(1).all()

@app.get("/api/signals")
def get_signals(db: Session = Depends(get_db)):
    return db.query(db_models.SignalLog).order_by(db_models.SignalLog.timestamp.desc()).limit(20).all()

@app.get("/api/analytics")
def get_analytics(db: Session = Depends(get_db)):
    return {"status": "ok", "message": "Analytics endpoint active"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
