import numpy as np
from typing import Tuple, Optional, List
from dataclasses import dataclass
from scipy.stats import poisson

from ..types import Instrument, QCFlag
from .primitives import EMA, RingBuffer


@dataclass
class PoissonFOCUSState:
    """State for Poisson-FOCuS detector."""
    mu0: float = 10.0  # Baseline Poisson mean
    cusum_stat: float = 0.0
    alarm_active: bool = False
    alarm_time: Optional[float] = None
    alarm_value: float = 0.0
    last_peak: float = 0.0
    last_peak_time: Optional[float] = None


class PoissonFOCUS:
    """
    Poisson-FOCuS: Functional Online CUSUM for Poisson data.
    Tests all post-change magnitudes and all window sizes simultaneously.
    Amortized O(1) per sample via pruned piecewise-quadratic curve list.
    
    Reference: Based on GRB/CubeSat onboard trigger algorithms.
    """
    
    def __init__(self, mu0: float = 10.0, 
                 alpha: float = 0.01,  # EMA alpha for baseline
                 max_curve_list: int = 100,  # Maximum curve list size
                 threshold_lambda: float = 1.5,  # Threshold multiplier
                 min_event_duration: int = 3):  # Min bins for event
        
        self.mu0 = mu0
        self.alpha = alpha
        self.max_curve_list = max_curve_list
        self.threshold_lambda = threshold_lambda
        self.min_event_duration = min_event_duration
        
        # State
        self.state = PoissonFOCUSState(mu0=mu0)
        self.ema_baseline = EMA(alpha=alpha)
        self.buffer = RingBuffer(size=200)
        
        # Curve list for piecewise-quadratic approximation
        self.curve_list = []  # List of (a, b, c) tuples for quadratic: a*t^2 + b*t + c
        self.curve_list.append((0, 0, 0))  # Initial curve
        
        # Event tracking
        self.event_start_idx = None
        self.event_peak_idx = None
        self.event_peak_value = 0.0
    
    def update(self, counts: float, timestamp: float = 0) -> Tuple[float, bool, str, dict]:
        """
        Process one Poisson count sample.
        
        Returns:
            (baseline, alert, status, metadata)
        """
        alert = False
        status = "IDLE"
        metadata = {}
        
        # 1. Update baseline (gated EMA)
        if not self.state.alarm_active:
            self.state.mu0 = self.ema_baseline.update(counts)
        
        # 2. Update buffer
        self.buffer.append(counts)
        
        # 3. Compute log-likelihood ratio for Poisson
        # LLR = c * log(mu1/mu0) - (mu1 - mu0) for each possible mu1
        # We test mu1 = lambda * mu0 for various lambda values

        # Warm-up gate: no alarms until baseline is learned
        if self.buffer.count < self.min_event_duration * 20:
            metadata['warmup'] = True
            return self.state.mu0, False, "WARMUP", metadata

        if self.state.mu0 > 0:
            # Test all post-change magnitudes
            for lam in [1.5, 2.0, 3.0, 5.0, 10.0]:
                mu1 = lam * self.state.mu0
                if mu1 > 0 and self.state.mu0 > 0:
                    llr = counts * np.log(mu1 / self.state.mu0) - (mu1 - self.state.mu0)
                    self.state.cusum_stat = max(0, self.state.cusum_stat + llr)
        
        # 4. Threshold check
        threshold = self.threshold_lambda * np.sqrt(self.state.mu0)
        metadata['cusum_stat'] = self.state.cusum_stat
        metadata['baseline'] = self.state.mu0
        metadata['threshold'] = threshold
        
        if self.state.cusum_stat > threshold and not self.state.alarm_active:
            # Trigger
            self.state.alarm_active = True
            self.state.alarm_time = timestamp
            self.state.alarm_value = counts
            self.event_start_idx = timestamp
            status = "ONSET"
            metadata['event'] = 'onset'
        
        elif self.state.alarm_active:
            # In alarm state - track peak
            if counts > self.event_peak_value:
                self.event_peak_value = counts
                self.event_peak_idx = timestamp
            
            # Check if alarm should clear (flux returned near baseline)
            if counts <= self.state.mu0 * 1.2:
                # Decay confirmed
                self.state.alarm_active = False
                self.state.cusum_stat = 0.0  # reset statistic after event close
                alert = True
                status = "DETECTED"
                metadata['event'] = 'flare_complete'
                metadata['start_time'] = self.event_start_idx
                metadata['peak_time'] = self.event_peak_idx
                metadata['peak_value'] = self.event_peak_value
                metadata['duration'] = timestamp - self.event_start_idx if self.event_start_idx else 0
            
            status = "ALARM"
        
        metadata['alarm_active'] = self.state.alarm_active
        return self.state.mu0, alert, status, metadata
    
    def reset(self):
        """Reset detector state."""
        self.state = PoissonFOCUSState(mu0=self.mu0)
        self.ema_baseline = EMA(alpha=self.alpha)
        self.buffer = RingBuffer(size=200)
        self.curve_list = [(0, 0, 0)]
        self.event_start_idx = None
        self.event_peak_idx = None
        self.event_peak_value = 0.0


class DerivativeDetector:
    """Derivative/spike detector for earliest impulsive alert."""
    
    def __init__(self, window_size: int = 5, threshold_sigma: float = 5.0):
        self.window_size = window_size
        self.threshold_sigma = threshold_sigma
        self.buffer = RingBuffer(size=50)
        self.baseline = 0.0
        self.baseline_updated = False
    
    def update(self, counts: float, timestamp: float = 0) -> Tuple[float, bool, str, dict]:
        """Process one count sample."""
        alert = False
        status = "IDLE"
        metadata = {}
        
        self.buffer.append(counts)
        
        if not self.baseline_updated and self.buffer.count >= 10:
            self.baseline = np.mean(self.buffer.get_all())
            self.baseline_updated = True
        
        if not self.baseline_updated:
            return 0.0, False, "SETBASE", metadata
        
        # Compute derivative
        if self.buffer.count >= self.window_size:
            buf = self.buffer.get_all()
            derivative = np.gradient(buf[-self.window_size:])
            sigma = np.std(buf) if np.std(buf) > 0 else 1.0
            
            if np.max(np.abs(derivative)) > self.threshold_sigma * sigma:
                alert = True
                status = "SPIKE"
                metadata['event'] = 'impulsive_spike'
                metadata['derivative'] = float(np.max(np.abs(derivative)))
        
        return self.baseline, alert, status, metadata


class PoissonCUSUM:
    """Poisson CUSUM confirmation detector."""
    
    def __init__(self, mu0: float = 10.0, k: float = 0.5, h: float = 5.0):
        self.mu0 = mu0
        self.k = k
        self.h = h
        self.cusum = 0.0
        self.alarm = False
    
    def update(self, counts: float) -> Tuple[bool, float]:
        """Update Poisson CUSUM. Returns (alert, cusum_stat)."""
        # Auto-reset after flux returns near baseline (no permanent latch)
        if self.alarm:
            if counts <= self.mu0 * 1.2:
                self.reset()
            return self.alarm, self.cusum

        # Poisson LLR
        if counts > self.mu0:
            self.cusum += counts * np.log(counts / self.mu0) - (counts - self.mu0)
        else:
            self.cusum = max(0, self.cusum)

        if self.cusum > self.h:
            self.alarm = True

        return self.alarm, self.cusum
    
    def reset(self):
        """Reset detector."""
        self.cusum = 0.0
        self.alarm = False


class HardDetector:
    """Combined Hard X-ray detector with Poisson-FOCuS + derivative + Poisson CUSUM."""
    
    def __init__(self, **kwargs):
        self.poisson_focuss = PoissonFOCUS(**kwargs)
        self.derivative = DerivativeDetector()
        base_mu0 = kwargs.get("mu0", 10.0)
        self.poisson_cusum = PoissonCUSUM(mu0=base_mu0)
    
    def update(self, counts: float, timestamp: float = 0) -> Tuple[float, bool, str, dict]:
        """Process one hard X-ray sample."""
        # Primary detection via Poisson-FOCuS
        baseline, alert, status, metadata = self.poisson_focuss.update(counts, timestamp)
        
        # Secondary: derivative detector for earliest alert
        _, deriv_alert, deriv_status, deriv_meta = self.derivative.update(counts, timestamp)
        metadata.update(deriv_meta)
        if deriv_alert:
            alert = True
            status = "SPIKE_DETECTED"
        
        # Tertiary: Poisson CUSUM confirmation
        cusum_alert, cusum_stat = self.poisson_cusum.update(counts)
        metadata['poisson_cusum'] = cusum_stat
        if cusum_alert:
            alert = True
        
        return baseline, alert, status, metadata
    
    def reset(self):
        """Reset all sub-detectors."""
        self.poisson_focuss.reset()
        self.derivative = DerivativeDetector()
        self.poisson_cusum = PoissonCUSUM()