import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from ai_engine import engine
from traffic_logic import traffic_controller
from websocket_manager import manager
import uvicorn
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Traffic Management AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for MJPEG stream
latest_frame = None

async def ai_loop():
    global latest_frame
    logger.info("Starting AI loop...")
    
    # Run the generator in a background thread to avoid blocking asyncio
    loop = asyncio.get_running_loop()
    generator = engine.process_stream()
    
    while True:
        try:
            # Get next frame & detections
            frame_bytes, detections, fps, inference_time = await loop.run_in_executor(None, next, generator)
            latest_frame = frame_bytes
            
            # Update traffic logic
            state_dict = traffic_controller.update(detections, fps, inference_time)
            
            # Broadcast to UI
            await manager.broadcast_state(state_dict)
            
            # Control loop rate (e.g., target ~10-15 FPS for the WebSocket updates to not overwhelm the UI)
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
            # We don't expect much from the client, just keep connection open
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def generate_mjpeg():
    global latest_frame
    while True:
        if latest_frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        time.sleep(0.05)
import time

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
