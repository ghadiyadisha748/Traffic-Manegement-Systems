from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class VehicleCounts(BaseModel):
    Car: int = 0
    Motorcycle: int = 0
    Bus: int = 0
    Truck: int = 0
    Person: int = 0
    TrafficSign: int = 0

class SignalLane(BaseModel):
    name: str
    arm: str
    time: int
    state: str

class CameraStats(BaseModel):
    fps: float
    inference_time: float
    confidence: float

class SystemHealth(BaseModel):
    backend: str
    yolo: str
    ws: str
    latency: int

class Weather(BaseModel):
    icon: str
    temp: str
    cond: str
    note: str

class TrafficState(BaseModel):
    counts: VehicleCounts
    total_count: int
    ped_timer: str
    wait_time: int
    fuel_saved: float
    co2_cut: int
    lane_load: int
    predict_pct: int
    predict_mins: int
    lanes: List[SignalLane]
    emergency: Dict[str, Any]
    signboard: List[str]
    weather: Weather
    camera: CameraStats
    health: SystemHealth
    logs: List[str]
    chart_vehicles: List[int]
    chart_congestion: List[int]
