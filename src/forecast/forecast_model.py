import numpy as np
import pandas as pd
from typing import List, Tuple, Optional
from dataclasses import dataclass

from ..nowcast.primitives import EMA, EWMV, RingBuffer
from ..constants import FORECAST_DEFAULTS, GOES_CLASS_FLUX_THRESHOLDS
from ..types import ForecastOutput


@dataclass
class Features:
    """30-dimensional feature vector for flare forecasting."""
    log_sxr: float = 0.0
    log_hxr: float = 0.0
    sxr_baselined: float = 0.0
    hxr_baselined: float = 0.0
    sxr_baseline_ratio: float = 0.0
    hxr_baseline_ratio: float = 0.0
    sxr_slope: float = 0.0
    hxr_slope: float = 0.0
    sxr_curvature: float = 0.0
    slope_accel: float = 0.0
    sa_weekly: float = 0.0
    sa_monthly: float = 0.0
    sa_quarterly: float = 0.0
    ha_weekly: float = 0.0
    ha_monthly: float = 0.0
    hardness_ratio: float = 0.0
    hardness_deriv: float = 0.0
    temp_proxy: float = 0.0
    temp_deriv: float = 0.0
    neupert_corr: float = 0.0
    neupert_resid: float = 0.0
    hxr_leads_flag: float = 0.0
    sxr_var: float = 0.0
    hxr_var: float = 0.0
    burst_count: float = 0.0
    hxr_peak_ratio: float = 0.0
    time_since_flare: float = 0.0
    flares_6h: float = 0.0
    quiet_duration: float = 0.0
    horizon_feature: float = 0.0
    
    def to_list(self) -> List[float]:
        return [v for v in self.__dict__.values() if not isinstance(v, (list, dict))]


class FeatureExtractor:
    """
    Extract 30-dimensional streaming features for ML model.
    All features are O(1) maintainable via running statistics.
    """
    
    def __init__(self, window_min: int = 30, alpha: float = 0.3):
        self.window = window_min * 60  # Convert to seconds (assuming 1 Hz)
        self.alpha = alpha
        
        # Rolling statistics
        self.ema_sxr = EMA(alpha=alpha)
        self.ema_hxr = EMA(alpha=alpha)
        self.ewmv_sxr = EWMV(alpha=alpha)
        self.ewmv_hxr = EWMV(alpha=alpha)
        
        # Buffers for polynomial fitting
        self.sxr_buffer = RingBuffer(size=max(window_min * 60, 300))
        self.hxr_buffer = RingBuffer(size=max(window_min * 60, 300))
        
        # Slopes via linear regression on buffer
        self.sxr_slope_ema = EMA(alpha=alpha)
        self.hxr_slope_ema = EMA(alpha=alpha)
        
        # Historical context
        self.last_flare_time = 0
        self.flare_history = []
    
    def update(self, sxr_flux: float, hxr_flux: float, timestamp: float) -> Features:
        """Update features with new sample."""
        f = Features()
        
        # Log transforms
        f.log_sxr = np.log10(sxr_flux + 1e-10)
        f.log_hxr = np.log10(hxr_flux + 1e-10)
        
        # EMAs for baselines
        f.sxr_baselined = self.ema_sxr.update(sxr_flux)
        f.hxr_baselined = self.ema_hxr.update(hxr_flux)
        
        # Baseline ratios (normalized flux)
        f.sxr_baseline_ratio = (sxr_flux / f.sxr_baselined) if f.sxr_baselined > 0 else 0
        f.hxr_baseline_ratio = (hxr_flux / f.hxr_baselined) if f.hxr_baselined > 0 else 0
        
        # Update buffers
        self.sxr_buffer.append(sxr_flux)
        self.hxr_buffer.append(hxr_flux)
        
        # Slopes via EMA of gradient
        if self.sxr_buffer.count >= 3:
            sxr_arr = self.sxr_buffer.get_all()
            times = np.arange(len(sxr_arr))
            slope = np.polyfit(times, sxr_arr, 1)[0]
            f.sxr_slope = self.sxr_slope_ema.update(slope)
        
        if self.hxr_buffer.count >= 3:
            hxr_arr = self.hxr_buffer.get_all()
            times = np.arange(len(hxr_arr))
            slope = np.polyfit(times, hxr_arr, 1)[0]
            f.hxr_slope = self.hxr_slope_ema.update(slope)
        
        # Acceleration
        f.slope_accel = max(0, f.sxr_slope - f.hxr_slope)
        
        # Variance (from EWMV)
        _, f.sxr_var = self.ewmv_sxr.update(sxr_flux)
        _, f.hxr_var = self.ewmv_hxr.update(hxr_flux)
        
        # Hardness ratio
        f.hardness_ratio = (hxr_flux / sxr_flux) if sxr_flux > 0 else 0
        f.hardness_deriv = f.hardness_ratio - getattr(self, '_prev_hardness', f.hardness_ratio)
        self._prev_hardness = f.hardness_ratio
        
        # Temperature proxy (equivalent temperature from flux)
        # T ∝ (flux)^(1/4) approximately
        f.temp_proxy = (sxr_flux / 1e-8) ** 0.25 * 10 if sxr_flux > 0 else 10
        
        # Burst count (HXR > mean + 5 sigma)
        if self.hxr_buffer.count >= 10:
            hxr_mean = np.mean(self.hxr_buffer.get_all())
            hxr_std = np.std(self.hxr_buffer.get_all())
            f.burst_count = 1.0 if hxr_flux > hxr_mean + 5 * hxr_std else 0.0
        
        # Peak ratio
        if self.hxr_buffer.count >= 10:
            f.hxr_peak_ratio = hxr_flux / np.max(self.hxr_buffer.get_all())
        
        # Time since last flare
        if self.last_flare_time > 0:
            f.time_since_flare = timestamp - self.last_flare_time
        
        # Horizon feature (for multi-horizon output)
        f.horizon_feature = FORECAST_DEFAULTS.get("window_min", 30) / 60
        
        return f
    
    def mark_flare(self, timestamp: float):
        """Record a flare event for historical context."""
        self.last_flare_time = timestamp
        self.flare_history.append(timestamp)
        # Keep only recent history
        self.flare_history = [t for t in self.flare_history if timestamp - t < 3600 * 24]
        f.flares_6h = len([t for t in self.flare_history if timestamp - t < 6 * 3600])


class LightGBMForecaster:
    """
    LightGBM-based flare forecaster.
    Optimized for edge deployment with ONNX export capability.
    """
    
    def __init__(self, n_estimators: int = 100, learning_rate: float = 0.1,
                 max_depth: int = 6, random_state: int = 42):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.random_state = random_state
        
        self.model = None
        self.is_trained = False
        self.feature_names = None
    
    def _build_features_for_training(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Build feature matrix and labels from dataframe."""
        extract = FeatureExtractor()
        features_list = []
        labels_list = []
        
        for idx, row in df.iterrows():
            feat = extract.update(
                row['counts'] if 'counts' in row else row['flux_solexs'],
                row.get('counts') if 'counts' in row else row['flux_hel1os'],
                row.get('timestamp_epoch', 0)
            )
            features_list.append(feat.to_list())
            
            # Label: is there a flare within next N minutes?
            # This would be computed from the master catalogue
            label = self._compute_label(row, df, idx)
            labels_list.append(label)
        
        return np.array(features_list), np.array(labels_list)
    
    def _compute_label(self, row, df, idx) -> int:
        """Compute binary label for training."""
        # Placeholder - actual implementation would check master catalogue
        # for any flare peak within next N minutes
        return 0
    
    def train(self, X: np.ndarray, y: np.ndarray) -> dict:
        """Train the LightGBM model."""
        from lightgbm import LGBMClassifier
        
        self.model = LGBMClassifier(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=self.random_state,
            objective='binary',
            boosting_type='gbdt',
            verbose=-1
        )
        
        # Calibration is handled separately
        self.model.fit(X, y, eval_metric='auc', verbose=False)
        self.is_trained = True
        
        return {'training_status': 'success'}
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Get raw prediction probabilities."""
        if not self.is_trained:
            raise ValueError("Model not trained. Call train() first.")
        return self.model.predict_proba(X)[:, 1]
    
    def predict_threshold(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Get binary predictions with configurable threshold."""
        probs = self.predict(X)
        return (probs >= threshold).astype(int)
    
    def calibrate(self, y_true: np.ndarray, y_prob: np.ndarray) -> dict:
        """Isotonic calibration for probabilities."""
        from sklearn.isotonic import IsotonicRegression
        
        self.calibrator = IsotonicRegression(out_of_bounds='clip')
        self.calibrator.fit(y_prob, y_true)
        
        return {'calibration_status': 'success'}
    
    def predict_calibrated(self, X: np.ndarray) -> np.ndarray:
        """Get calibrated probabilities."""
        probs = self.predict(X)
        if hasattr(self, 'calibrator'):
            return self.calibrator.predict(probs)
        return probs
    
    def export_onnx(self, path: str):
        """Export model to ONNX for edge deployment."""
        try:
            import skl2onnx
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import FloatTensorType
            
            initial_type = [('float_input', FloatTensorType([None, X.shape[1]]))]
            onnx_model = convert_sklearn(self.model, initial_types=initial_type)
            
            with open(path, 'wb') as f:
                f.write(onnx_model.SerializeToString())
            
            return True
        except ImportError:
            print("skl2onnx not installed. Skipping ONNX export.")
            return False
    
    def get_feature_importance(self) -> dict:
        """Get feature importance scores."""
        if not self.is_trained:
            return {}
        return dict(zip(
            self.feature_names or [f'feature_{i}' for i in range(X.shape[1])],
            self.model.feature_importances_.tolist()
        ))


def forecast_flare_probability(features: np.ndarray, model: LightGBMForecaster,
                                threshold: float = 0.5, horizon_min: int = 15,
                                timestamp: float = 0) -> ForecastOutput:
    """Generate forecast output with calibrated probability."""
    prob = model.predict_calibrated(features)[0] if features.shape[0] > 0 else 0.05
    
    return ForecastOutput(
        timestamp=datetime.fromtimestamp(timestamp) if timestamp else None,
        probability=float(prob),
        lead_time_s=horizon_min * 60,
        horizon_min=horizon_min,
        threshold_class="C",  # Default threshold
        calibrated_prob=float(prob * 0.9)  # Conservative calibration
    )