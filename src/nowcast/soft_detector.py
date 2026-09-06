import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass

from ..types import Instrument, QCFlag
from .primitives import EMA, EWMV, P2Quantile, HampelDespiker, RingBuffer


@dataclass
class DetectorState:
    """State for a single detector."""
    baseline: float = 0.0
    cusum_stat: float = 0.0
    ema_state: float = 0.0
    fsm_state: str = "IDLE"
    consecutive_min: int = 0
    peak_detected: bool = False
    last_peak_time: Optional[float] = None
    last_peak_value: float = 0.0


class CUSUMDetector:
    """
    CUSUM (Cumulative Sum) Change-Point Detector for Soft X-rays.
    O(1) per sample. Uses one-sided upper CUSUM to detect flux increases.
    """
    
    def __init__(self, alpha: float = 0.1,
                 baseline_window: int = 600,  # seconds
                 cusum_k: float = 1.0,
                 h_c_sigma: float = 5.0,
                 min_height_sigma: float = 5.0,
                 cusum_k_sigma: Optional[float] = None):
        # cusum_k_sigma, if set, makes the slack unit-free: k = cusum_k_sigma*sigma.
        # Required for real physical-unit streams (W/m^2), where an absolute
        # slack would dwarf the signal.
        self.alpha = alpha
        self.baseline_window = baseline_window
        self.cusum_k = cusum_k
        self.cusum_k_sigma = cusum_k_sigma
        self.h_c_sigma = h_c_sigma
        self.min_height_sigma = min_height_sigma
        
        # State
        self.state = DetectorState()
        self.ema_baseline = EMA(alpha=0.01)  # Very slow EMA for baseline
        self.ewmv = EWMV(alpha=0.01)  # Slow variance
        self.hampel = HampelDespiker(window_size=11, threshold_sigma=5.0)
        self.buffer = RingBuffer(size=max(baseline_window, 1000))
        
        # FSM parameters
        self.fsm_consecutive_min = 4
        self.fsm_ratio = 1.4
        
        # For flare characterization
        self.flare_start_idx = None
        self.flare_peak_idx = None
        self.flare_peak_value = 0.0
        self.warmup_min_samples = 60
        self._in_alarm = False
    
    def update(self, flux: float, timestamp: float = 0) -> Tuple[float, bool, str, dict]:
        """
        Process one flux sample.
        
        Returns:
            (baseline, alert, status, metadata)
        """
        alert = False
        status = "IDLE"
        metadata = {}

        # ---- Burn-in: seed baseline & variance from the warm-up window ----
        # (EMA-from-zero makes the detector fire on its own initialization
        #  artifact on real streams, then stay mis-calibrated.)
        self.buffer.append(flux)
        if self.buffer.count < self.warmup_min_samples:
            return 0.0, False, "WARMUP", {"warmup": True}
        if not getattr(self, "_seeded", False):
            buf = self.buffer.get_all()
            med = float(np.median(buf))
            self.ema_baseline.state = med          # seed, don't crawl from 0
            mad = float(np.median(np.abs(buf - med)))
            scale = max(1.4826 * mad, float(np.std(buf)), 1e-9)
            self._last_var = scale * scale         # seed variance
            self._seeded = True

        # 1. Despike (remove cosmic rays, particle hits)
        flux_clean, is_spike = self.hampel.update(flux)
        metadata['is_spike'] = is_spike
        flux_for_baseline = flux_clean
        
        # 2. Update robust baseline (gated percentile EMA)
        if self.state.fsm_state in ["IDLE", "DONE"]:
            self.state.baseline = self.ema_baseline.update(flux_for_baseline)
            self.ewmv.update(flux_for_baseline)
        
        # 4. Sigma estimate - GATED variance
        if self.state.fsm_state in ["IDLE", "DONE"]:
            _, self._last_var = self.ewmv.update(flux_for_baseline)
        sigma = float(np.sqrt(max(getattr(self, "_last_var", 1.0), 1e-12)))
        self.state.ema_state = sigma
        
        # 5. CUSUM update
        k_eff = (
            self.cusum_k_sigma * sigma
            if self.cusum_k_sigma is not None
            else self.cusum_k
        )
        deviation = flux_clean - self.state.baseline
        self.state.cusum_stat = max(0.0, self.state.cusum_stat + deviation - k_eff)
        
        metadata['cusum_stat'] = self.state.cusum_stat
        metadata['baseline'] = self.state.baseline
        metadata['sigma'] = sigma
        metadata['deviation'] = deviation
        
        # 6. Adaptive Relative Ratio & CUSUM Threshold Check
        ratio = (flux_clean / self.state.baseline) if self.state.baseline > 0 else 1.0
        threshold = self.h_c_sigma * sigma
        metadata['threshold'] = threshold
        warmed_up = self.buffer.count >= self.warmup_min_samples

        if not warmed_up:
            status = "WARMUP"
            metadata['fsm_state'] = self.state.fsm_state
            return self.state.baseline, False, status, metadata

        # Trigger on either statistical CUSUM deviation or 25%+ relative solar flux excess
        is_onset_condition = (self.state.cusum_stat > threshold or ratio >= 1.25)

        if is_onset_condition and self.state.fsm_state in ["IDLE", "DONE"] and not self._in_alarm:
            self.state.fsm_state = "INCREASING"
            self._in_alarm = True
            self.state.consecutive_min = 0
            self.state.peak_detected = False
            self.flare_start_idx = timestamp
            self._flare_baseline = float(self.state.baseline)
            self.flare_peak_value = flux_clean
            self.flare_peak_idx = timestamp
            status = "ONSET"
            metadata['event'] = 'onset'
        
        elif self.state.fsm_state in ["INCREASING", "SUSTAINED"]:
            # Track peak maximum
            if flux_clean > self.flare_peak_value:
                self.flare_peak_value = flux_clean
                self.flare_peak_idx = timestamp
            
            # Transition to decaying once past peak and starts dropping
            if flux_clean < self.flare_peak_value * 0.95:
                self.state.fsm_state = "DECAYING"
                status = "DECAYING"
            else:
                status = "INCREASING"
        
        elif self.state.fsm_state == "DECAYING":
            # Re-peak check (multi-stage eruption)
            if flux_clean > self.flare_peak_value * 1.05:
                self.flare_peak_value = flux_clean
                self.flare_peak_idx = timestamp
                status = "REPEAK"
            else:
                # GOES standard 1/2 decay completion rule
                half_level = self._flare_baseline + 0.5 * (self.flare_peak_value - self._flare_baseline)
                time_in_flare = (timestamp - self.flare_start_idx) if self.flare_start_idx else 0
                
                if flux_clean <= half_level or time_in_flare > 7200:
                    self.state.fsm_state = "DONE"
                    self._in_alarm = False
                    self.state.cusum_stat = 0.0
                    alert = True
                    status = "DETECTED"
                    metadata['event'] = 'flare_complete'
                    metadata['start_time'] = self.flare_start_idx
                    metadata['peak_time'] = self.flare_peak_idx
                    metadata['peak_value'] = self.flare_peak_value
                    metadata['duration'] = time_in_flare
                else:
                    status = "DECAYING"
        
        metadata['fsm_state'] = self.state.fsm_state
        return self.state.baseline, alert, status, metadata
    
    def reset(self):
        """Reset detector state."""
        self.state = DetectorState()
        self.ema_baseline = EMA(alpha=0.01)
        self.ewmv = EWMV(alpha=0.01)
        self.hampel = HampelDespiker(window_size=11, threshold_sigma=5.0)
        self.buffer = RingBuffer(size=max(self.baseline_window, 1000))
        self.flare_start_idx = None
        self.flare_peak_idx = None
        self.flare_peak_value = 0.0


class GOESFSMClassifier:
    """GOES-style Finite State Machine for flare classification."""
    
    GOES_THRESHOLDS = {
        'A': 1e-8,
        'B': 1e-7,
        'C': 1e-6,
        'M': 1e-5,
        'X': 1e-4,
    }
    
    def __init__(self):
        self.current_class = 'A'
    
    def classify_flux(self, peak_flux: float) -> str:
        """Classify peak flux into GOES class."""
        for cls in ['X', 'M', 'C', 'B', 'A']:
            if peak_flux >= self.GOES_THRESHOLDS[cls]:
                return cls
        return 'A'
    
    def get_subclass(self, peak_flux: float) -> str:
        """Get GOES class with numeric subclass."""
        goes_class = self.classify_flux(peak_flux)
        threshold = self.GOES_THRESHOLDS[goes_class]
        sub = peak_flux / threshold
        return f"{goes_class}{sub:.1f}"


class SoftDetector:
    """Combined Soft X-ray detector with CUSUM + GOES FSM."""
    
    def __init__(self, **kwargs):
        self.cusum = CUSUMDetector(**kwargs)
        self.classifier = GOESFSMClassifier()
    
    def update(self, flux: float, timestamp: float = 0) -> Tuple[float, bool, str, dict]:
        return self.cusum.update(flux, timestamp)
    
    def classify(self, peak_flux: float) -> str:
        return self.classifier.get_subclass(peak_flux)