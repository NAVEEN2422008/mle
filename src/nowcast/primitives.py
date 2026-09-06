import numpy as np
from scipy.signal import argrelextrema
from typing import List

from ..types import QCFlag


class EMA:
    """Exponentially Weighted Moving Average - O(1) per update."""
    
    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self.state = 0.0
    
    def update(self, x: float) -> float:
        self.state = self.alpha * x + (1 - self.alpha) * self.state
        return self.state


class EWMV:
    """Exponentially Weighted Moving Variance - O(1) per update."""
    
    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self.state = 0.0  # mean
        self.variance = 1.0  # variance
    
    def update(self, x: float) -> tuple[float, float]:
        self.state = self.alpha * x + (1 - self.alpha) * self.state
        diff = x - self.state
        self.variance = self.alpha * (diff ** 2) + (1 - self.alpha) * self.variance
        return self.state, self.variance


class P2Quantile:
    """P² Quantile algorithm - O(1) median + MAD estimation."""
    
    def __init__(self, n_quantiles: int = 5):
        self.n_quantiles = n_quantiles
        self.marker_positions = np.arange(1, n_quantiles + 1) / (n_quantiles + 1)
        self.quantiles = np.zeros(n_quantiles)
        self.quantiles_updated = np.zeros(n_quantiles, dtype=bool)
        self.g_min = 0.0
        self.g_max = 1.0
        self.old_q = np.zeros(n_quantiles)
    
    def update(self, x: float) -> tuple[float, float]:
        if not np.any(self.quantiles_updated):
            self.quantiles[0] = x
            self.quantiles_updated[0] = True
            return x, 0.0
        
        # Find where x lies
        i = 0
        while i < self.n_quantiles and x > self.quantiles[i]:
            i += 1
        
        if i == 0:
            self.old_q[0] = self.quantiles[0]
            self.quantiles[0] = x
        elif i == self.n_quantiles:
            self.old_q[-1] = self.quantiles[-1]
            self.quantiles[-1] = x
        else:
            self.old_q[i-1] = self.quantiles[i-1]
            self.old_q[i] = self.quantiles[i]
            self.quantiles[i-1] = x
        
        # Update other quantiles
        self.g_min = 0.0
        self.g_max = 1.0
        
        for k in range(self.n_quantiles):
            if self.quantiles_updated[k]:
                delta = (self.quantiles[k] - self.old_q[k]) / (
                    self.marker_positions[k] - self.g_min)
                self.g_max = min(self.g_max, delta)
                self.g_min = max(self.g_min, delta)
        
        # Update quantile values based on deltas
        g = self.g_min + (self.g_max - self.g_min) / 2
        for k in range(self.n_quantiles):
            if self.quantiles_updated[k]:
                self.quantiles[k] = self.old_q[k] + g * (
                    self.marker_positions[k] - self.g_min)
        
        median = self.quantiles[self.n_quantiles // 2]
        mad = 1.4826 * np.median(np.abs(self.quantiles - median))
        
        return median, mad


class HampelDespiker:
    """Hampel filter for outlier detection - O(1) per sample."""
    
    def __init__(self, window_size: int = 11, threshold_sigma: float = 3.0):
        self.window_size = window_size
        self.threshold_sigma = threshold_sigma
        self.buffer = []
    
    def update(self, x: float) -> tuple[float, bool]:
        self.buffer.append(x)
        
        if len(self.buffer) > self.window_size:
            self.buffer.pop(0)
        
        if len(self.buffer) < 3:
            return x, False
        
        median = np.median(self.buffer)
        mad = 1.4826 * np.median(np.abs(np.array(self.buffer) - median))
        std = np.std(self.buffer)
        
        sigma = mad if mad > 0 else std
        if sigma == 0:
            return x, False
        
        if np.abs(x - median) > self.threshold_sigma * sigma:
            return median, True
        
        return x, False


class RingBuffer:
    """Fixed-size ring buffer - O(1) per operation."""
    
    def __init__(self, size: int = 100):
        self.size = size
        self.buffer = np.zeros(size)
        self.head = 0
        self.count = 0
    
    def append(self, x: float) -> None:
        self.buffer[self.head] = x
        self.head = (self.head + 1) % self.size
        if self.count < self.size:
            self.count += 1
    
    def get_all(self) -> np.ndarray:
        if self.count == self.size:
            return self.buffer.copy()
        else:
            return self.buffer[:self.count]
    
    def is_full(self) -> bool:
        return self.count >= self.size


def format_time_series(df, signal_col, timestamp_col, window_size=10, max_outliers=2):
    """Format time series data with robust outlier handling."""
    df = df.sort_values(timestamp_col).reset_index(drop=True)
    
    # Detrend using rolling median
    df['rolling_median'] = df[signal_col].rolling(window=window_size, center=True, min_periods=1).median()
    
    # Identify outliers
    df['deviation'] = np.abs(df[signal_col] - df['rolling_median'])
    df['mad'] = df['deviation'].rolling(window=window_size, center=True, min_periods=1).apply(
        lambda x: np.median(np.abs(x - np.median(x))) * 1.4826 if len(x) > 0 else 0,
        raw=True
    )
    df['sigma_est'] = df['mad'].replace(0, df['deviation'].std())
    
    # Clip extreme outliers
    df['cleaned'] = np.where(
        df['deviation'] > 5 * df['sigma_est'],
        df['rolling_median'],
        df[signal_col]
    )
    
    return df


# Statistics helper
from scipy.stats import median_abs_deviation


def robust_statistics(series, window=11):
    """Compute robust statistics using rolling median and MAD."""
    rolling_median = series.rolling(window=window, center=True, min_periods=1).median()
    mad = series.rolling(window=window, center=True, min_periods=1).apply(
        lambda x: median_abs_deviation(x, scale='normal') if len(x) > 0 else 0,
        raw=True
    )
    std = series.rolling(window=window, center=True, min_periods=1).std()
    
    # Use MAD when available, otherwise std
    sigma = mad.fillna(std)
    
    return {
        'median': rolling_median,
        'mad': mad,
        'std': std,
        'sigma': sigma,
        'normalized': (series - rolling_median) / sigma
    }