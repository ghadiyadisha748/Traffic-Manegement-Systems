from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base
import datetime

class TrafficHistory(Base):
    __tablename__ = "traffic_history"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    total_count = Column(Integer)
    avg_wait_time = Column(Integer)
    co2_cut = Column(Integer)

class VehicleDetection(Base):
    __tablename__ = "vehicle_detections"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    track_id = Column(Integer, index=True)
    vehicle_type = Column(String)
    lane = Column(String)
    speed = Column(Float)
    wait_time = Column(Integer)

class SignalLog(Base):
    __tablename__ = "signal_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    lane_name = Column(String)
    duration_sec = Column(Integer)
    reason = Column(String)

class Intersection(Base):
    __tablename__ = "intersections"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    location = Column(String)
    status = Column(String)

class EmergencyEvent(Base):
    __tablename__ = "emergency_events"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    vehicle_type = Column(String)
    lane = Column(String)
    duration_sec = Column(Integer)

class PredictionHistory(Base):
    __tablename__ = "prediction_history"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    congestion_pct = Column(Integer)
    predicted_delay_mins = Column(Integer)

class SystemHealthLog(Base):
    __tablename__ = "system_health_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    fps = Column(Float)
    latency = Column(Integer)
