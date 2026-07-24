import time
from collections import deque
from models import TrafficState, VehicleCounts, SignalLane, CameraStats, SystemHealth, Weather
from database import SessionLocal
import db_models

class TrafficController:
    def __init__(self):
        self.chart_vehicles = deque([0] * 12, maxlen=12)
        self.chart_congestion = deque([0] * 12, maxlen=12)
        self.logs = deque(["SYSTEM INITIALIZED — AI Engine Online"], maxlen=6)
        
        self.total_cycle = 120
        self.ped_timer = 20
        self.emergency_active = False
        
        self.lanes = [
            {"name": "Road A", "arm": "N", "queue": 0},
            {"name": "Road B", "arm": "E", "queue": 0},
            {"name": "Road C", "arm": "S", "queue": 0},
            {"name": "Road D", "arm": "W", "queue": 0}
        ]
        
        self.weather_state = {
            "icon": "☀️", "temp": "31°C", 
            "cond": "CLEAR", 
            "note": "Confidence normal."
        }
        
        # Track memory for wait times
        self.tracked_vehicles = {} # id -> {first_seen: float, lane: str}

        self.last_db_save = time.time()

    def log(self, msg: str):
        t = time.strftime("%H:%M:%S")
        self.logs.append(f'<span class="ts">{t}</span>{msg}')

    def update(self, detections, fps, inference_time):
        current_counts = {"Car": 0, "Motorcycle": 0, "Bus": 0, "Truck": 0, "Person": 0, "TrafficSign": 0}
        lane_queues = {"Road A": 0, "Road B": 0, "Road C": 0, "Road D": 0, "Pedestrian Crossing": 0}
        
        now = time.time()
        active_ids = set()
        
        emergency_detected = False

        for det in detections:
            cls = det['class_name']
            track_id = det['track_id']
            lane = det['lane']
            active_ids.add(track_id)
            
            # Counts
            if cls in ["car"]: current_counts["Car"] += 1
            elif cls in ["motorcycle", "bicycle"]: current_counts["Motorcycle"] += 1
            elif cls in ["bus"]: current_counts["Bus"] += 1
            elif cls in ["truck"]: current_counts["Truck"] += 1
            elif cls in ["person"]: current_counts["Person"] += 1
            elif cls in ["stop sign", "traffic light"]: current_counts["TrafficSign"] += 1
            
            if cls in ["ambulance", "fire truck", "police"]:
                emergency_detected = True

            # Tracking wait times
            if track_id not in self.tracked_vehicles:
                self.tracked_vehicles[track_id] = {"first_seen": now, "lane": lane}
            
            # Queue calculation
            if lane in lane_queues:
                lane_queues[lane] += 1

        # Cleanup lost tracks
        for tid in list(self.tracked_vehicles.keys()):
            if tid not in active_ids:
                del self.tracked_vehicles[tid]

        # Calculate average wait time based on tracked ID persistence
        total_wait = 0
        if self.tracked_vehicles:
            for v in self.tracked_vehicles.values():
                total_wait += (now - v["first_seen"])
            avg_wait = int(total_wait / len(self.tracked_vehicles))
        else:
            avg_wait = 0

        # Pedestrian logic based on ROI occupancy
        if lane_queues.get("Pedestrian Crossing", 0) > 3:
            self.ped_timer = 25 # Increase crossing time due to crowd
        else:
            self.ped_timer -= 0.5
            if self.ped_timer <= 0:
                self.ped_timer = 20

        # Emergency Priority
        if emergency_detected and not self.emergency_active:
            self.emergency_active = True
            self.log("EMERGENCY VEHICLE DETECTED — GREEN CORRIDOR ACTIVE")
        elif not emergency_detected and self.emergency_active:
            self.emergency_active = False
            self.log("EMERGENCY CLEARED — RESUMING NORMAL OPERATION")

        total = sum(current_counts.values())
        
        # Adaptive Signal Timing based on REAL ROI queue length
        lane_sum = sum([lane_queues[l["name"]] for l in self.lanes]) or 1
        
        for l in self.lanes:
            l["queue"] = lane_queues[l["name"]]
            
        max_idx = max(range(len(self.lanes)), key=lambda i: self.lanes[i]["queue"])
        
        signal_lanes = []
        for i, l in enumerate(self.lanes):
            share = l["queue"] / lane_sum
            time_sec = max(12, int(self.total_cycle * share))
            
            if self.emergency_active:
                state = "green" if i == 0 else "red" # Force Road A for demo logic if emergency
            else:
                state = "green" if i == max_idx else ("amber" if share > 0.15 else "red")
            
            signal_lanes.append(SignalLane(
                name=l["name"], arm=l["arm"], time=time_sec, state=state
            ))

        # Metrics based on real data
        fuel_saved = round((avg_wait / 60.0) * 1.5, 1) # Heuristic using real wait
        co2_cut = max(0, min(100, int((len(active_ids) * 2) - avg_wait)))
        
        # Congestion Score = vehicles / capacity
        capacity_assumed = 40
        lane_load = min(100, int((total / capacity_assumed) * 100))
        predict_pct = min(100, lane_load + int(avg_wait / 10))
        predict_mins = max(3, int(15 - predict_pct / 10))

        # Update historical charts every ~5 seconds
        if int(now) % 5 == 0 and now - getattr(self, '_last_chart_update', 0) > 1:
            self.chart_vehicles.append(total)
            self.chart_congestion.append(predict_pct)
            self._last_chart_update = now

        # DB Logging every 10s
        if now - self.last_db_save > 10:
            self.last_db_save = now
            try:
                db = SessionLocal()
                hist = db_models.TrafficHistory(total_count=total, avg_wait_time=avg_wait, co2_cut=co2_cut)
                db.add(hist)
                db.commit()
                db.close()
            except Exception as e:
                pass

        signboard = [
            f"> {self.lanes[max_idx]['name']}: HEAVY QUEUE ({self.lanes[max_idx]['queue']})",
            "> AI OPTIMIZING SIGNALS",
            f"AVG DELAY: {avg_wait}s"
        ]
        if self.emergency_active:
            signboard = ["> EMERGENCY OVERRIDE", "> CLEAR CORRIDOR", "> ALL LANES STOP"]

        state = TrafficState(
            counts=VehicleCounts(**current_counts),
            total_count=total,
            ped_timer=f"{int(self.ped_timer)}s",
            wait_time=avg_wait,
            fuel_saved=fuel_saved,
            co2_cut=co2_cut,
            lane_load=lane_load,
            predict_pct=predict_pct,
            predict_mins=predict_mins,
            lanes=signal_lanes,
            emergency={"active": self.emergency_active, "message": "Priority Vehicle Detected"},
            signboard=signboard,
            weather=Weather(**self.weather_state),
            camera=CameraStats(fps=round(fps, 1), inference_time=round(inference_time, 1), confidence=0.85),
            health=SystemHealth(backend="ONLINE", yolo="ACTIVE", ws="CONNECTED", latency=15),
            logs=list(self.logs),
            chart_vehicles=list(self.chart_vehicles),
            chart_congestion=list(self.chart_congestion)
        )
        return state.model_dump()

traffic_controller = TrafficController()
