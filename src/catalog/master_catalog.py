"""Master flare catalogue: hash-bucket O(1) index, cross-band merge, dedup.

Design (per PLAN.md v2 / ARCHITECTURE research):
- Time-bucketed index: bucket(t) = epoch_s // BUCKET_S. Insert O(1),
  point query O(1), range query O(#buckets spanned).
- Cross-band association uses the Neupert prior: HXR onset <= SXR onset and
  HXR peak < SXR peak by seconds-to-minutes. Asymmetric windows.
- De-dup: sub-peaks of one complex flare are merged unless separated by a
  clean return-to-baseline plus guard gap GUARD_S.
- Confidence: noisy-OR over contributing detections, plus Neupert bonus.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..types import FlareEvent, Instrument
from ..constants import GOES_CLASS_FLUX_THRESHOLDS

BUCKET_S = 3600          # 1-hour buckets
GUARD_S = 120            # min separation for two distinct flares
W_LEAD_S = 300           # hard may lead soft by up to 5 min
W_LAG_S = 900            # soft decay can lag hard peak by up to 15 min


def classify_flux_goes(peak_flux_wm2: float) -> str:
    """Closed-form GOES class from 1-8 A peak flux (O(1))."""
    if peak_flux_wm2 >= GOES_CLASS_FLUX_THRESHOLDS["X"]:
        return "X"
    if peak_flux_wm2 >= GOES_CLASS_FLUX_THRESHOLDS["M"]:
        return "M"
    if peak_flux_wm2 >= GOES_CLASS_FLUX_THRESHOLDS["C"]:
        return "C"
    if peak_flux_wm2 >= GOES_CLASS_FLUX_THRESHOLDS["B"]:
        return "B"
    return "A"


def goes_subclass(peak_flux_wm2: float) -> str:
    """GOES class with numeric mantissa, e.g. M2.5 == 2.5e-5 W/m2."""
    cls = classify_flux_goes(peak_flux_wm2)
    mantissa = peak_flux_wm2 / GOES_CLASS_FLUX_THRESHOLDS[cls]
    return f"{cls}{mantissa:.1f}"


@dataclass
class Detection:
    """A single-band detection awaiting association."""
    instrument: Instrument
    t_start: datetime
    t_peak: datetime
    t_end: datetime
    peak_value: float       # instrument-native units (counts or W/m2)
    p_detect: float         # detector confidence in [0,1]
    band: str               # "soft" | "hard"

    @property
    def bucket(self) -> int:
        return int(self.t_peak.timestamp()) // BUCKET_S


@dataclass
class CatalogueStats:
    n_events: int = 0
    n_merged: int = 0
    n_deduped: int = 0
    n_neupert_verified: int = 0


class MasterCatalogue:
    """Time-bucketed store of merged flare events."""

    def __init__(self) -> None:
        self._buckets: Dict[int, List[FlareEvent]] = {}
        self._by_id: Dict[str, FlareEvent] = {}
        self.stats = CatalogueStats()
        self._next_id = 1

    # ---------- indexing primitives (all O(1)) ----------

    def _bucket_of(self, ts: datetime) -> int:
        return int(ts.timestamp()) // BUCKET_S

    def insert(self, event: FlareEvent) -> FlareEvent:
        event.event_id = f"FL{self._next_id:06d}"
        self._next_id += 1
        b = self._bucket_of(event.peak_time)
        self._buckets.setdefault(b, []).append(event)
        self._by_id[event.event_id] = event
        self.stats.n_events += 1
        return event

    def query_near(self, ts: datetime) -> List[FlareEvent]:
        """Point query: events in the bucket containing ts (O(1))."""
        return list(self._buckets.get(self._bucket_of(ts), []))

    def query_range(self, start: datetime, end: datetime) -> List[FlareEvent]:
        """Range query: O(#buckets spanned + hits)."""
        b0 = self._bucket_of(start)
        b1 = self._bucket_of(end)
        out: List[FlareEvent] = []
        for b in range(b0, b1 + 1):
            out.extend(self._buckets.get(b, []))
        return sorted(out, key=lambda e: e.peak_time)

    @property
    def all_events(self) -> List[FlareEvent]:
        return sorted(self._by_id.values(), key=lambda e: e.peak_time)

    # ---------- association ----------

    def associate(
        self,
        soft_dets: List[Detection],
        hard_dets: List[Detection],
        baseline_soft: float = 0.0,
    ) -> List[FlareEvent]:
        """Merge per-band detections into master events (Neupert-aware).

        Score combines asymmetric temporal overlap and the Neupert prior
        that the hard peak precedes the soft peak.
        """
        used_hard: set[int] = set()
        events: List[FlareEvent] = []

        for sd in soft_dets:
            best: Optional[Tuple[float, Detection]] = None
            best_j: Optional[int] = None
            for j, hd in enumerate(hard_dets):
                if j in used_hard:
                    continue
                dt = (sd.t_peak - hd.t_peak).total_seconds()  # >0 => HXR earlier
                if dt < -W_LEAD_S:      # HXR way after soft: not Neupert-like
                    continue
                if dt > W_LAG_S:        # too far apart entirely
                    continue
                # reward Neupert-consistent ordering (HXR first)
                neupert_bonus = 0.25 if 0.0 <= dt <= W_LEAD_S else 0.0
                proximity = 1.0 - abs(dt) / max(W_LEAD_S + W_LAG_S, 1)
                score = proximity + neupert_bonus
                if best is None or score > best[0]:
                    best = (score, hd)
                    best_j = j

            if best is not None and best_j is not None and best[0] >= 0.4:
                hd = best[1]
                used_hard.add(best_j)
                self.stats.n_merged += 1
                neupert_ok = hd.t_peak <= sd.t_peak
                if neupert_ok:
                    self.stats.n_neupert_verified += 1
                confidence = float(min(1.0, 1.0 - (1.0 - sd.p_detect) * (1.0 - hd.p_detect)))
                if neupert_ok:
                    confidence = min(1.0, confidence + 0.05)
                event = FlareEvent(
                    start_time=min(sd.t_start, hd.t_start),
                    peak_time=sd.t_peak,
                    end_time=max(sd.t_end, hd.t_end),
                    peak_flux_solexs=float(sd.peak_value),
                    peak_flux_hel1os=float(hd.peak_value),
                    goes_class=classify_flux_goes(sd.peak_value),
                    confidence=confidence,
                    instrument_flags=Instrument.SOLEXS_SDD2 | Instrument.HEL1OS_CDTE,
                    neupert_verified=neupert_ok,
                    duration_s=(max(sd.t_end, hd.t_end) - min(sd.t_start, hd.t_start)).total_seconds(),
                )
                events.append(event)
            else:
                # soft-only event still enters catalogue (HXR-quiet flare class)
                events.append(
                    FlareEvent(
                        start_time=sd.t_start,
                        peak_time=sd.t_peak,
                        end_time=sd.t_end,
                        peak_flux_solexs=float(sd.peak_value),
                        peak_flux_hel1os=0.0,
                        goes_class=classify_flux_goes(sd.peak_value),
                        confidence=float(sd.p_detect),
                        instrument_flags=Instrument.SOLEXS_SDD2,
                        neupert_verified=False,
                        duration_s=(sd.t_end - sd.t_start).total_seconds(),
                    )
                )

        # unmatched hard-only detections are kept: HXR-only events are
        # scientifically valuable (non-thermal-dominated, GOES-invisible)
        for j, hd in enumerate(hard_dets):
            if j in used_hard:
                continue
            events.append(
                FlareEvent(
                    start_time=hd.t_start,
                    peak_time=hd.t_peak,
                    end_time=hd.t_end,
                    peak_flux_solexs=0.0,
                    peak_flux_hel1os=float(hd.peak_value),
                    goes_class="HXR-only",
                    confidence=float(hd.p_detect),
                    instrument_flags=Instrument.HEL1OS_CDTE,
                    neupert_verified=False,
                    duration_s=(hd.t_end - hd.t_start).total_seconds(),
                )
            )

        for ev in sorted(events, key=lambda e: e.peak_time):
            self.insert(ev)
        return self.all_events

    # ---------- dedup ----------

    def dedupe(self) -> int:
        """Merge same-class events that begin within GUARD_S of the previous
        event's ORIGINAL end (no chaining through extended end times)."""
        removed = 0
        events = self.all_events
        kept: List[Tuple[FlareEvent, datetime]] = []  # (event, original_end)
        for ev in events:
            dup = False
            for pair in kept:
                prev, orig_end = pair
                gap = (ev.start_time - orig_end).total_seconds()
                if gap < GUARD_S and ev.goes_class == prev.goes_class:
                    prev.end_time = max(prev.end_time, ev.end_time)
                    prev.peak_flux_solexs = max(prev.peak_flux_solexs, ev.peak_flux_solexs)
                    prev.peak_flux_hel1os = max(prev.peak_flux_hel1os, ev.peak_flux_hel1os)
                    prev.confidence = max(prev.confidence, ev.confidence)
                    prev.neupert_verified = prev.neupert_verified or ev.neupert_verified
                    prev.duration_s = (
                        prev.end_time - prev.start_time
                    ).total_seconds()
                    dup = True
                    removed += 1
                    break
            if not dup:
                kept.append((ev, ev.end_time))

        if removed:
            rebuilt = [p[0] for p in kept]
            self._rebuild(rebuilt)
            self.stats.n_deduped += removed
        return removed

    def _rebuild(self, events: List[FlareEvent]) -> None:
        self._buckets.clear()
        self._by_id.clear()
        self.stats.n_events = 0
        self._next_id = 1
        for ev in events:
            ev.event_id = ""
            self.insert(ev)

    # ---------- persistence ----------

    def to_dataframe(self):
        import pandas as pd

        rows = [
            {
                "event_id": e.event_id,
                "detection_timestamp": e.start_time,
                "start_time": e.start_time,
                "peak_time": e.peak_time,
                "end_time": e.end_time,
                "duration_s": e.duration_s,
                "solexs_peak_flux": e.peak_flux_solexs,
                "hel1os_peak_flux": e.peak_flux_hel1os,
                "estimated_class": e.goes_class,
                "confidence_score": round(e.confidence, 3),
                "neupert_verified": e.neupert_verified,
            }
            for e in self.all_events
        ]
        return pd.DataFrame(rows)

    def export_sqlite(self, db_path: str = "data/master_flare_catalog.db") -> str:
        """Export master flare catalog to SQLite matching the hackathon schema."""
        import sqlite3
        from pathlib import Path
        
        p = Path(db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_flare_catalog (
                flare_id INTEGER PRIMARY KEY AUTOINCREMENT,
                detection_timestamp TIMESTAMP,
                start_time TIMESTAMP,
                peak_time TIMESTAMP,
                end_time TIMESTAMP,
                solexs_peak_flux REAL,
                hel1os_peak_flux REAL,
                estimated_class VARCHAR(10),
                confidence_score REAL
            )
        """)
        for e in self.all_events:
            cursor.execute("""
                INSERT INTO master_flare_catalog (
                    detection_timestamp, start_time, peak_time, end_time,
                    solexs_peak_flux, hel1os_peak_flux, estimated_class, confidence_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(e.start_time), str(e.start_time), str(e.peak_time), str(e.end_time),
                float(e.peak_flux_solexs), float(e.peak_flux_hel1os),
                e.goes_class, float(e.confidence)
            ))
        conn.commit()
        conn.close()
        return str(p.resolve())


def arbitrate_sdd(counts_sdd1: float, counts_sdd2: float, sat_cps: float = 1e5) -> Tuple[str, float]:
    """SoLEXS detector arbitration rule (calib paper).

    SDD1 saturates paralyzably above ~1e5 cps; above that trust SDD2 only.
    Returns (chosen_detector, trusted_counts).
    """
    if counts_sdd1 > sat_cps:
        return ("SDD2", counts_sdd2)
    return ("SDD1", counts_sdd1)
