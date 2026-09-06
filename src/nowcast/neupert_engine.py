import numpy as np
from typing import Tuple, Optional, List
from datetime import datetime

from ..types import Instrument, QCFlag, FlareEvent
from ..constants import NOWCAST_DEFAULTS, GOES_CLASS_FLUX_THRESHOLDS


class NeupertCorrelator:
    """
    Neupert Effect Correlation Engine.
    
    The Neupert effect states: F_HXR(t) ∝ d/dt F_SXR(t),
    equivalently F_SXR(t) ∝ ∫ F_HXR dt .
    
    Hard X-ray emission (HEL1OS) tracks the derivative of the soft X-ray emission (SoLEXS),
    and HXR peaks BEFORE the SXR peak by ~1-3 minutes.
    This engine validates this relationship and computes Neupert-based features.
    """
    
    def __init__(self, corr_window_s: float = 120, lag_s: float = 180):
        self.corr_window_s = corr_window_s
        self.lag_s = lag_s
        
        # State buffers
        self.sxr_window = []
        self.hxr_window = []
        self.timestamps = []
        
        # Results
        self.last_correlation = 0.0
        self.neupert_residual = 0.0
        self.hxr_leads = False
        self.peak_lag_s = 0.0
    
    def update(self, sxr_flux: float, hxr_flux: float, timestamp: float = 0) -> dict:
        """Feed in synchronized SXR/HXR samples."""
        self.timestamps.append(timestamp)
        self.sxr_window.append(sxr_flux)
        self.hxr_window.append(hxr_flux)
        
        # Maintain window size
        max_size = int(self.corr_window_s)  # Assuming 1 Hz
        if len(self.timestamps) > max_size:
            self.timestamps.pop(0)
            self.sxr_window.pop(0)
            self.hxr_window.pop(0)
        
        if len(self.sxr_window) < 10:
            return {
                'neupert_corr': 0.0,
                'neupert_resid': 0.0,
                'hxr_leads': False,
                'peak_lag_s': 0.0
            }
        
        # Compute SXR derivative (using gradient)
        sxr = np.array(self.sxr_window)
        hxr = np.array(self.hxr_window)
        
        if len(sxr) < 5:
            return {
                'neupert_corr': self.last_correlation,
                'neupert_resid': self.neupert_residual,
                'hxr_leads': self.hxr_leads,
                'peak_lag_s': self.peak_lag_s
            }
        
        # Compute derivative of SXR
        dsxr_dt = np.gradient(sxr)
        
        # Normalize for correlation
        dsxr_norm = dsxr_dt - np.mean(dsxr_dt)
        hxr_norm = hxr - np.mean(hxr)
        
        dsxr_std = np.std(dsxr_norm)
        hxr_std = np.std(hxr_norm)
        
        if dsxr_std > 0 and hxr_std > 0:
            correlation = np.corrcoef(dsxr_norm, hxr_norm)[0, 1]
        else:
            correlation = 0.0
        
        self.last_correlation = correlation
        
        # Compute Neupert residual (how well HXR matches dSXR/dt)
        # Scale factor
        if np.std(dsxr_dt) > 0 and np.std(hxr) > 0:
            alpha = np.corrcoef(dsxr_norm, hxr_norm)[0, 1] * np.std(hxr_norm) / np.std(dsxr_norm)
            predicted_hxr = alpha * dsxr_dt
            residual = hxr - predicted_hxr
            self.neupert_residual = float(np.mean(np.abs(residual)))
        else:
            self.neupert_residual = float(np.mean(np.abs(hxr)))
        
        # Check if HXR leads SXR (HXR peak before SXR peak)
        hxr_peak_idx = np.argmax(hxr)
        sxr_peak_idx = np.argmax(sxr)
        
        self.hxr_leads = hxr_peak_idx < sxr_peak_idx
        self.peak_lag_s = float((sxr_peak_idx - hxr_peak_idx) * 1.0)  # 1 Hz assumption
        
        return {
            'neupert_corr': float(correlation),
            'neupert_resid': self.neupert_residual,
            'hxr_leads': self.hxr_leads,
            'peak_lag_s': self.peak_lag_s
        }
    
    def get_features(self) -> List[float]:
        """Get Neupert-based features for ML model."""
        return [
            self.last_correlation,
            self.neupert_residual,
            1.0 if self.hxr_leads else 0.0,
            self.peak_lag_s,
        ]


class CrossBandAssociator:
    """
    Associate soft and hard X-ray detections using Neupert effect physics.
    """
    
    def __init__(self, t_assoc_window: float = 300, max_lag: float = 180):
        self.t_assoc_window = t_assoc_window  # seconds
        self.max_lag = max_lag  # maximum expected HXR-before-SXR lag
        self.detections = {'solexs': [], 'hel1os': []}
        self.matched_events = []
    
    def add_detection(self, instrument: Instrument, timestamp: datetime, 
                      peak_flux: float, confidence: float = 1.0):
        """Add a detection from either instrument."""
        if instrument == Instrument.SOLEXS_SDD2:
            self.detections['solexs'].append({
                'time': timestamp,
                'flux': peak_flux,
                'confidence': confidence
            })
        elif instrument in [Instrument.HEL1OS_CDTE, Instrument.HEL1OS_CZT]:
            self.detections['hel1os'].append({
                'time': timestamp,
                'flux': peak_flux,
                'confidence': confidence
            })
    
    def associate(self) -> List[FlareEvent]:
        """Associate detections and validate Neupert effect."""
        events = []
        
        for solexs_det in self.detections['solexs']:
            best_match = None
            best_score = 0
            
            for hel1os_det in self.detections['hel1os']:
                dt = abs((solexs_det['time'] - hel1os_det['time']).total_seconds())
                
                if dt > self.t_assoc_window:
                    continue
                
                # Neupert prior: HXR peak should precede SXR peak
                neupert_score = 0.0
                if hel1os_det['time'] < solexs_det['time']:
                    neupert_score = 0.3  # HXR before SXR (good)
                elif hel1os_det['time'] == solexs_det['time']:
                    neupert_score = 0.1  # Simultaneous (neutral)
                
                # Temporal proximity score
                time_score = 1.0 - dt / self.t_assoc_window
                
                total_score = time_score + neupert_score
                
                if total_score > best_score:
                    best_score = total_score
                    best_match = hel1os_det
            
            if best_match is not None and best_score > 0.5:
                # Create merged flare event
                start_time = min(solexs_det['time'], best_match['time'])
                peak_time = solexs_det['time']
                
                # Classify using SoLEXS flux (converted to GOES)
                goes_class = self._classify_flux(solexs_det['flux'])
                
                event = FlareEvent(
                    start_time=start_time,
                    peak_time=peak_time,
                    end_time=peak_time,  # Will be updated by detector
                    peak_flux_solexs=solexs_det['flux'],
                    peak_flux_hel1os=best_match['flux'],
                    goes_class=goes_class,
                    confidence=min(1.0, best_score + 0.2 * neupert_score),
                    instrument_flags=Instrument.SOLEXS_SDD2 | Instrument.HEL1OS_CDTE,
                    neupert_verified=best_match['time'] < solexs_det['time'],
                )
                events.append(event)
        
        return events
    
    def _classify_flux(self, flux: float) -> str:
        """Convert SoLEXS counts to GOES class."""
        # Simplified conversion - will use proper cross-calibration
        log_flux = np.log10(flux + 1e-10)
        if log_flux < 3:
            return "A"
        elif log_flux < 4:
            return "B"
        elif log_flux < 5:
            return "C"
        elif log_flux < 6:
            return "M"
        else:
            return "X"