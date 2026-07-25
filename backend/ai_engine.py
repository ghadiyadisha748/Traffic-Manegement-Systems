import cv2
import time
import numpy as np
from ultralytics import YOLO
from shapely.geometry import Point, Polygon
from collections import deque
from config import settings
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Debug flag — flip to True during calibration or development only.
# Has zero cost in normal operation (no branch taken, no extra objects drawn).
# ---------------------------------------------------------------------------
DEBUG_MODE = False

# ---------------------------------------------------------------------------
# Velocity thresholds  (pixels per SECOND — FPS-independent)
#
# Derivation: previous thresholds were 3 px/frame and 12 px/frame at ~20 FPS.
#   3  px/frame × 20 FPS =  60 px/s  →  STOP_SPEED_PX_PER_SEC
#  12  px/frame × 20 FPS = 240 px/s  →  QUEUE_SPEED_PX_PER_SEC
#
# These now stay correct at any camera frame rate.
# ---------------------------------------------------------------------------
STOP_SPEED_PX_PER_SEC  = 60.0    # px/s — vehicles at or below this are stationary
QUEUE_SPEED_PX_PER_SEC = 240.0   # px/s — vehicles at or below this are slow / queued

VELOCITY_HISTORY_FRAMES = 6   # number of (cx, cy, ts) positions kept per track
LANE_HISTORY_FRAMES     = 8   # sliding window length for lane-persistence vote

# ---------------------------------------------------------------------------
# ROI Definitions — relative polygon vertices, each (x, y) in [0.0, 1.0]
#
# Rectangles are expressed as 4-vertex lists; arbitrary polygons (trapezoids,
# hexagons, perspective-corrected shapes) work identically.  Change only the
# vertex coordinates here to adapt to a different camera angle or intersection
# geometry — no code changes required elsewhere.
#
# Ordering in ROI_PRIORITY determines which lane wins when a sample point
# falls inside multiple overlapping regions.  Road lanes always beat the
# Pedestrian Crossing centre-box so it acts purely as a catch-all fallback.
# ---------------------------------------------------------------------------
RELATIVE_ROI_POLYGONS: dict[str, list[tuple[float, float]]] = {
    "Road A":              [(0.28, 0.00), (0.72, 0.00), (0.72, 0.35), (0.28, 0.35)],
    "Road B":              [(0.65, 0.18), (1.00, 0.18), (1.00, 0.82), (0.65, 0.82)],
    "Road C":              [(0.28, 0.65), (0.72, 0.65), (0.72, 1.00), (0.28, 1.00)],
    "Road D":              [(0.00, 0.18), (0.35, 0.18), (0.35, 0.82), (0.00, 0.82)],
    "Pedestrian Crossing": [(0.25, 0.28), (0.75, 0.28), (0.75, 0.72), (0.25, 0.72)],
}

ROI_PRIORITY = ["Road A", "Road B", "Road C", "Road D", "Pedestrian Crossing"]

# Multi-point vote specification: (bx_fraction, by_fraction_from_bottom, weight)
#   bx_fraction          — horizontal position within the bounding box (0=left, 1=right)
#   by_fraction_from_bottom — vertical offset from the bottom edge (0=bottom, 1=top)
#   weight               — vote weight for this sample point
SAMPLE_POINT_SPECS: list[tuple[float, float, int]] = [
    (0.50, 0.05, 3),   # bottom-centre : best ground-plane proxy, highest weight
    (0.50, 0.50, 2),   # box centre    : overall vehicle body
    (0.25, 0.05, 1),   # bottom-left ¼ : wide-vehicle coverage
    (0.75, 0.05, 1),   # bottom-right ¼: wide-vehicle coverage
]   # total votes available per frame: 3+2+1+1 = 7


class AIEngine:
    def __init__(self):
        try:
            self.model = YOLO(settings.YOLO_MODEL)
            logger.info(f"Loaded YOLO model: {settings.YOLO_MODEL}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self.model = None

        # Pixel-space ROI polygons; rebuilt lazily when frame size changes.
        self._rois_px: dict[str, Polygon] = {}
        self._frame_size: tuple[int, int] = (0, 0)

        # Per-track state (keyed by integer ByteTrack ID):
        #   track_history    — deque[(cx, cy, timestamp)] for velocity
        #   track_lane_votes — deque[str] for lane-persistence window
        self.track_history:    dict[int, deque] = {}
        self.track_lane_votes: dict[int, deque] = {}

    # -----------------------------------------------------------------------
    # ROI helpers
    # -----------------------------------------------------------------------
    def _build_rois(self, W: int, H: int) -> None:
        """
        Materialise relative polygon vertex lists into pixel-space Shapely polygons.
        Called automatically whenever the frame dimensions change.
        """
        self._rois_px = {}
        for name, rel_vertices in RELATIVE_ROI_POLYGONS.items():
            px_vertices = [(int(rx * W), int(ry * H)) for rx, ry in rel_vertices]
            self._rois_px[name] = Polygon(px_vertices)
        self._frame_size = (W, H)
        logger.debug(f"ROIs rebuilt for {W}×{H}")

    def _get_rois(self, W: int, H: int) -> dict[str, Polygon]:
        if (W, H) != self._frame_size:
            self._build_rois(W, H)
        return self._rois_px

    # -----------------------------------------------------------------------
    # Lane assignment — step 1: multi-point weighted vote (single frame)
    # -----------------------------------------------------------------------
    def _vote_lane(self, x1: int, y1: int, x2: int, y2: int, W: int, H: int) -> str:
        """
        Cast a raw (single-frame) lane vote using multiple weighted sample points.

        Points are positioned relative to the bounding box so the algorithm
        is scale-invariant.  Each point votes for the first ROI (in priority
        order) that contains it; ties go to the higher-priority lane.
        """
        rois = self._get_rois(W, H)
        bw = x2 - x1
        bh = y2 - y1

        votes: dict[str, int] = {}
        for bx_frac, by_frac_from_bottom, weight in SAMPLE_POINT_SPECS:
            px = x1 + bw * bx_frac
            py = y2 - bh * by_frac_from_bottom
            pt = Point(px, py)
            for name in ROI_PRIORITY:
                if rois[name].contains(pt):
                    votes[name] = votes.get(name, 0) + weight
                    break   # each sample point votes for exactly one lane

        return max(votes, key=lambda k: votes[k]) if votes else "Unknown"

    # -----------------------------------------------------------------------
    # Lane assignment — step 2: recency-weighted persistence across frames
    # -----------------------------------------------------------------------
    def _assign_lane_with_weighted_vote(self, track_id: int, raw_lane: str) -> str:
        """
        Recency-weighted majority-vote lane persistence.

        Algorithm
        ---------
        A sliding window of the last LANE_HISTORY_FRAMES raw lane votes is
        maintained per track.  Votes are scored by position in the window:

            weight(frame) = position_in_window   (1 = oldest, N = newest)

        The lane with the highest total weighted score is returned.

        Why this beats simple unanimity
        --------------------------------
        • Single noisy frame:  gains at most weight N from one entry; the
          stable lane accumulates weights 1+2+…+(N-1) = N×(N-1)/2, which is
          always larger for N ≥ 3.  One bad frame cannot change the result.

        • Genuine transition:  as a vehicle moves steadily into a new ROI,
          recent frames (high weights) vote for the new lane while older frames
          (low weights) vote for the old one.  The new lane wins cleanly once
          it holds approximately the top half of the window.

        • No hyperparameter tuning per camera: adjusting LANE_HISTORY_FRAMES
          alone controls the trade-off between stability and response speed.
        """
        if track_id not in self.track_lane_votes:
            self.track_lane_votes[track_id] = deque(maxlen=LANE_HISTORY_FRAMES)

        window = self.track_lane_votes[track_id]
        window.append(raw_lane)

        # Score each lane: sum of its recency weights (1-indexed position)
        scored: dict[str, float] = {}
        for position, lane in enumerate(window, start=1):
            scored[lane] = scored.get(lane, 0.0) + position

        return max(scored, key=lambda k: scored[k])

    # -----------------------------------------------------------------------
    # Velocity (FPS-independent, px/s)
    # -----------------------------------------------------------------------
    def _compute_velocity(self, track_id: int, cx: float, cy: float, ts: float) -> float | None:
        """
        Estimate vehicle speed in pixels per second using timestamped positions.

        Stores up to VELOCITY_HISTORY_FRAMES entries of (cx, cy, timestamp).
        Returns None when fewer than two positions are available (first frame
        of a new track), so callers can treat initial appearance as unknown.

        Using wall-clock timestamps instead of frame counts means the result
        is identical whether the camera runs at 10, 20, or 30 FPS.
        """
        if track_id not in self.track_history:
            self.track_history[track_id] = deque(maxlen=VELOCITY_HISTORY_FRAMES)

        hist = self.track_history[track_id]
        hist.append((cx, cy, ts))

        if len(hist) < 2:
            return None

        total_dist = 0.0
        total_time = 0.0
        for i in range(1, len(hist)):
            dx = hist[i][0] - hist[i - 1][0]
            dy = hist[i][1] - hist[i - 1][1]
            dt = hist[i][2] - hist[i - 1][2]
            total_dist += (dx * dx + dy * dy) ** 0.5
            total_time += dt

        return (total_dist / total_time) if total_time > 0 else None

    # -----------------------------------------------------------------------
    # Stale-track cleanup
    # -----------------------------------------------------------------------
    def _cleanup_tracks(self, active_ids: set) -> None:
        """Discard state for track IDs not seen in the current frame."""
        for tid in list(self.track_history.keys()):
            if tid not in active_ids:
                del self.track_history[tid]
        for tid in list(self.track_lane_votes.keys()):
            if tid not in active_ids:
                del self.track_lane_votes[tid]

    # -----------------------------------------------------------------------
    # Debug overlay  (only called when DEBUG_MODE = True)
    # -----------------------------------------------------------------------
    def _draw_debug_overlay(
        self,
        frame: np.ndarray,
        detections: list,
        lane_queue_counts: dict[str, int],
    ) -> None:
        """
        Rich diagnostic overlay.  Draws:
          - All ROI polygons with name labels at their centroids
          - Per-vehicle: bounding box, track ID, class, lane, speed (px/s),
            motion state, queue status indicator
          - Top-right panel: queued vehicle count per lane
        """
        H, W = frame.shape[:2]
        rois = self._get_rois(W, H)

        # --- ROI polygons + centroid labels ---
        for name, poly in rois.items():
            pts = np.array(poly.exterior.coords, np.int32).reshape((-1, 1, 2))
            color = (255, 80, 0) if "Pedestrian" in name else (0, 200, 255)
            cv2.polylines(frame, [pts], True, color, 2, cv2.LINE_AA)
            cx_r = int(poly.centroid.x)
            cy_r = int(poly.centroid.y)
            cv2.putText(frame, name, (cx_r - 28, cy_r),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)

        # --- Per-vehicle bounding boxes + telemetry ---
        STATE_COLORS = {
            "stationary": (0, 0, 255),
            "slow":       (0, 165, 255),
            "moving":     (0, 220, 0),
        }
        for det in detections:
            x1, y1, x2, y2 = det["box"]
            motion    = det["motion_state"]
            box_color = STATE_COLORS.get(motion, (180, 180, 180))
            spd       = det["velocity"]
            spd_str   = f"{spd:.0f}px/s" if spd is not None else "---"
            q_flag    = "[Q]" if det["is_queued"] else "   "

            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
            # Line 1: ID + class + lane
            cv2.putText(
                frame,
                f"#{det['track_id']} {det['class_name']} | {det['lane']}",
                (x1, y1 - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.33, (255, 255, 255), 1, cv2.LINE_AA,
            )
            # Line 2: motion state + speed + queue flag
            cv2.putText(
                frame,
                f"{motion} {spd_str} {q_flag}",
                (x1, y1 - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.30, box_color, 1, cv2.LINE_AA,
            )
            cv2.circle(frame, (int((x1 + x2) / 2), int((y1 + y2) / 2)),
                       3, (0, 0, 255), -1)

        # --- Queue-count panel (top-right corner) ---
        road_lanes = [n for n in ROI_PRIORITY if n != "Pedestrian Crossing"]
        panel_w    = 162
        panel_h    = len(road_lanes) * 18 + 10
        px         = W - panel_w - 4
        py         = 6
        cv2.rectangle(frame, (px - 2, py - 2), (W - 4, py + panel_h),
                      (20, 20, 20), -1)
        cv2.rectangle(frame, (px - 2, py - 2), (W - 4, py + panel_h),
                      (80, 80, 80), 1)
        for i, lane in enumerate(road_lanes):
            count = lane_queue_counts.get(lane, 0)
            color = (0, 60, 220) if count > 3 else (60, 200, 80)
            cv2.putText(
                frame,
                f"{lane[:7]}: {count:2d} queued",
                (px + 4, py + i * 18 + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1, cv2.LINE_AA,
            )

    # -----------------------------------------------------------------------
    # Main stream generator
    # -----------------------------------------------------------------------
    def process_stream(self):
        """
        Yields (frame_bytes, detections, fps, inference_time) for each frame.

        Each detection dict contains:
          lane          — stabilised lane label (recency-weighted vote)
          velocity      — speed in px/s, or None on first appearance
          motion_state  — "stationary" | "slow" | "moving"
          is_queued     — True when stationary or slow-moving
        """
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
                cv2.putText(frame, "NO VIDEO SOURCE", (150, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            H, W      = frame.shape[:2]
            frame_ts  = time.time()
            fps       = 1.0 / (frame_ts - prev_time + 0.001)
            prev_time = frame_ts

            inf_start         = time.time()
            detections        = []
            active_ids        = set()
            lane_queue_counts = {name: 0 for name in ROI_PRIORITY}

            # Lightweight ROI outlines in normal mode only
            # (DEBUG mode draws thicker labelled versions in _draw_debug_overlay)
            if not DEBUG_MODE:
                rois = self._get_rois(W, H)
                for name, poly in rois.items():
                    pts = np.array(poly.exterior.coords, np.int32).reshape((-1, 1, 2))
                    color = (255, 0, 0) if "Pedestrian" in name else (0, 255, 255)
                    cv2.polylines(frame, [pts], True, color, 1)

            if self.model and cap:
                results = self.model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    verbose=False,
                    conf=settings.CONFIDENCE_THRESHOLD,
                )[0]
                print("Boxes:", results.boxes)

                if results.boxes is not None and results.boxes.id is not None:
                    print("Track IDs:", results.boxes.id)
                    boxes     = results.boxes.xyxy.cpu().numpy()
                    track_ids = results.boxes.id.int().cpu().tolist()
                    clss      = results.boxes.cls.cpu().tolist()
                    confs     = results.boxes.conf.cpu().tolist()

                    for box, track_id, cls_id, conf in zip(boxes, track_ids, clss, confs):
                        cls_name = self.model.names[int(cls_id)]
                        
                        x1, y1, x2, y2 = map(int, box)
                        print("Detected:", cls_name)
                        cx = (x1 + x2) / 2.0
                        cy = (y1 + y2) / 2.0

                        active_ids.add(track_id)

                        # Step 1: per-frame multi-point vote
                        raw_lane = self._vote_lane(x1, y1, x2, y2, W, H)
                        # Step 2: recency-weighted persistence across frames
                        lane = self._assign_lane_with_weighted_vote(track_id, raw_lane)

                        # Step 3: FPS-independent velocity → motion state
                        velocity = self._compute_velocity(track_id, cx, cy, frame_ts)

                        if velocity is None:
                            motion_state = "moving"   # insufficient history; safe default
                            is_queued    = False
                        elif velocity <= STOP_SPEED_PX_PER_SEC:
                            motion_state = "stationary"
                            is_queued    = True
                        elif velocity <= QUEUE_SPEED_PX_PER_SEC:
                            motion_state = "slow"
                            is_queued    = True
                        else:
                            motion_state = "moving"
                            is_queued    = False

                        if is_queued and lane in lane_queue_counts:
                            lane_queue_counts[lane] += 1

                        detections.append({
                            "track_id":     track_id,
                            "class_name":   cls_name,
                            "confidence":   float(conf),
                            "box":          [x1, y1, x2, y2],
                            "center":       [int(cx), int(cy)],
                            "lane":         lane,
                            "velocity":     round(velocity, 1) if velocity is not None else None,
                            "motion_state": motion_state,
                            "is_queued":    is_queued,
                        })

                        # Normal-mode overlay: colour-coded box only
                        if not DEBUG_MODE:
                            box_color = {
                                "stationary": (0, 0, 255),
                                "slow":       (0, 165, 255),
                                "moving":     (0, 255, 0),
                            }.get(motion_state, (200, 200, 200))
                            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                            label = f"ID:{track_id} {cls_name} [{motion_state}] ({lane})"
                            cv2.putText(frame, label, (x1, y1 - 8),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
                            cv2.circle(frame, (int(cx), int(cy)), 3, (0, 0, 255), -1)

            # Full debug overlay (only when DEBUG_MODE = True)
            if DEBUG_MODE:
                self._draw_debug_overlay(frame, detections, lane_queue_counts)

            self._cleanup_tracks(active_ids)

            inference_time = (time.time() - inf_start) * 1000

            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"Inf: {inference_time:.1f}ms", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            ret, buffer = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70]
            )
            print("Detections created:", len(detections))
            yield buffer.tobytes(), detections, fps, inference_time


engine = AIEngine()
