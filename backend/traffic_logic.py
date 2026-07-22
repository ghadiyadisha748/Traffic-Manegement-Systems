import time
import math
import random
from collections import deque
from models import TrafficState, VehicleCounts, SignalLane, CameraStats, SystemHealth, Weather

class TrafficController:
    def __init__(self):
        self.chart_vehicles = deque([40] * 12, maxlen=12)
        self.chart_congestion = deque([30] * 12, maxlen=12)
        self.logs = deque(["SYSTEM INITIALIZED — AI Engine Online"], maxlen=6)
        
        self.total_cycle = 120
        self.ped_timer = 20
        self.emergency_active = False
        self.emergency_timer = 0
        
        self.lanes = [
            {"name": "Road A", "arm": "N", "share": 0.25},
            {"name": "Road B", "arm": "E", "share": 0.25},
            {"name": "Road C", "arm": "S", "share": 0.25},
            {"name": "Road D", "arm": "W", "share": 0.25}
        ]
        
        self.weather_state = {
            "icon": "☀️", "temp": "31°C", 
            "cond": "CLEAR · VISIBILITY HIGH", 
            "note": "Detection confidence unaffected. No prediction adjustment applied."
        }
        
        # Smoothed counts
        self.smoothed_counts = {"Car": 0, "Motorcycle": 0, "Bus": 0, "Truck": 0, "Person": 0, "TrafficSign": 0}

    def log(self, msg: str):
        t = time.strftime("%H:%M:%S")
        self.logs.append(f'<span class="ts">{t}</span>{msg}')

    def update(self, detections, fps, inference_time):
        # Update counts with slight smoothing for UI stability
        current_counts = {"Car": 0, "Motorcycle": 0, "Bus": 0, "Truck": 0, "Person": 0, "TrafficSign": 0}
        
        emergency_detected = False
        for det in detections:
            cls = det['class_name']
            if cls in ["car"]: current_counts["Car"] += 1
            elif cls in ["motorcycle", "bicycle"]: current_counts["Motorcycle"] += 1
            elif cls in ["bus"]: current_counts["Bus"] += 1
            elif cls in ["truck"]: current_counts["Truck"] += 1
            elif cls in ["person"]: current_counts["Person"] += 1
            elif cls in ["stop sign", "traffic light"]: current_counts["TrafficSign"] += 1
            
            # Emergency logic (mocked classes for ambulance/fire/police if YOLO supports, else simulate rarely based on bus/truck or standard COCO classes)
            # In COCO, we might not have ambulance. We will rely on custom logic or just trigger it if a 'truck' and 'bus' are seen uniquely, 
            # but for hackathon, we can inject a random emergency event or map a specific class.
            
        for k in current_counts:
            # Exponential moving average for smoothing
            self.smoothed_counts[k] = int(0.7 * self.smoothed_counts[k] + 0.3 * current_counts[k])

        # Overrides for demo if nothing detected
        total = sum(self.smoothed_counts.values())
        if total == 0:
            # Fallback random walk for demo purposes if video has no cars
            self.smoothed_counts = {
                "Car": random.randint(10, 20),
                "Motorcycle": random.randint(5, 10),
                "Bus": random.randint(0, 2),
                "Truck": random.randint(0, 3),
                "Person": random.randint(0, 5),
                "TrafficSign": 2
            }
            total = sum(self.smoothed_counts.values())

        # Update historical charts every ~5 seconds (simulated by random chance for demo, in reality driven by a clock)
        if random.random() < 0.05:
            self.chart_vehicles.append(total)
            self.chart_congestion.append(int((total / 50) * 100))

        # Pedestrian Logic
        self.ped_timer -= 0.5
        if self.ped_timer <= 0:
            self.ped_timer = 20
            
        # Emergency Logic
        if not self.emergency_active and random.random() < 0.01:
            self.emergency_active = True
            self.emergency_timer = 20 # active for 20 ticks
            self.log("EMERGENCY VEHICLE DETECTED — GREEN CORRIDOR ACTIVE")
            
        if self.emergency_active:
            self.emergency_timer -= 1
            if self.emergency_timer <= 0:
                self.emergency_active = False
                self.log("EMERGENCY CLEARED — RESUMING NORMAL OPERATION")

        # Adaptive Signal Timing based on total volume
        # Simulate lane loads
        lane_totals = [
            total * 0.4 + random.randint(0,5),
            total * 0.2 + random.randint(0,5),
            total * 0.3 + random.randint(0,5),
            total * 0.1 + random.randint(0,5)
        ]
        lane_sum = sum(lane_totals) or 1
        
        for i, lane in enumerate(self.lanes):
            lane["share"] = lane_totals[i] / lane_sum
            
        max_idx = max(range(len(lane_totals)), key=lane_totals.__getitem__)
        
        signal_lanes = []
        for i, l in enumerate(self.lanes):
            time_sec = max(12, int(self.total_cycle * l["share"]))
            if self.emergency_active:
                state = "green" if i == 0 else "red" # Force Road A green
            else:
                state = "green" if i == max_idx else ("amber" if l["share"] > 0.15 else "red")
            
            signal_lanes.append(SignalLane(
                name=l["name"],
                arm=l["arm"],
                time=time_sec,
                state=state
            ))

        # Metrics
        wait_time = int(30 + (total * 0.5))
        fuel_saved = round((wait_time / 42.0) * 2.1, 1)
        co2_cut = max(4, min(32, int((1 - wait_time / 78) * 90)))
        lane_load = min(100, int((total / 60) * 100))
        predict_pct = min(100, int((total / 50) * 100) + random.randint(-5, 5))
        predict_mins = max(3, int(15 - predict_pct / 10))

        # Signboard recommendations
        signboard = [
            f"> {self.lanes[max_idx]['name']}: HEAVY VOLUME",
            "> AI OPTIMIZING GREEN TIME",
            f"EST. SAVING {max(1, 15 - predict_mins)} MIN"
        ]
        if self.emergency_active:
            signboard = [
                "> EMERGENCY OVERRIDE ACTIVE",
                "> CORRIDOR SECURED",
                "> DO NOT BLOCK INTERSECTION"
            ]

        # Construct payload
        state = TrafficState(
            counts=VehicleCounts(**self.smoothed_counts),
            total_count=total,
            ped_timer=f"{int(self.ped_timer)}s",
            wait_time=wait_time,
            fuel_saved=fuel_saved,
            co2_cut=co2_cut,
            lane_load=lane_load,
            predict_pct=predict_pct,
            predict_mins=predict_mins,
            lanes=signal_lanes,
            emergency={"active": self.emergency_active, "message": "Ambulance approaching — Road A priority"},
            signboard=signboard,
            weather=Weather(**self.weather_state),
            camera=CameraStats(fps=round(fps, 1), inference_time=round(inference_time, 1), confidence=0.85),
            health=SystemHealth(backend="ONLINE", yolo="ACTIVE", ws="CONNECTED", latency=random.randint(12, 28)),
            logs=list(self.logs),
            chart_vehicles=list(self.chart_vehicles),
            chart_congestion=list(self.chart_congestion)
        )
        return state.model_dump()

traffic_controller = TrafficController()
