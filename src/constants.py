# Physical constants and configuration values
SPEED_OF_LIGHT_KMS = 299792.458   # km/s
AU_KM = 149597870.7               # Earth-Sun distance in km
AU_M = 149597870700.0             # Earth-Sun distance in meters

L1_HELIOCENTRIC_AU = 0.990        # Aditya-L1 heliocentric distance (AU)
EARTH_HELIOCENTRIC_AU = 1.000     # Earth heliocentric distance (AU)

# Light-travel-time offsets to Earth reference frame (seconds)
LTT_OFFSET_ADITYA_L1_S = 5.0
LTT_OFFSET_SOLAR_ORBITER_S = 249.0
LTT_OFFSET_STEREO_A_S = 20.0
LTT_OFFSET_PARKER_S = 476.0

# Compatibility aliases for legacy imports (do not use in new code)
LIGHT_SPEED_URL = SPEED_OF_LIGHT_KMS
SOLAR_C = SPEED_OF_LIGHT_KMS
L1_HELIocentric_AU = L1_HELIOCENTRIC_AU
EARTH_HELIocentric_AU = EARTH_HELIOCENTRIC_AU
EARTH_HELIOcetric_AU = EARTH_HELIOCENTRIC_AU

# Instrument areas (mm^2)
SOLEXS_SDD1_AREA_MM2 = 7.1    # large aperture (quiet-Sun / small flares)
SOLEXS_SDD2_AREA_MM2 = 0.1    # small aperture (M/X-class, saturates SDD1)

SOLEXS_ENERGY_RANGE_KEV = (2.0, 22.0)
HEL1OS_CDTE_RANGE_KEV = (8.0, 70.0)
HEL1OS_CZT_RANGE_KEV = (20.0, 150.0)

# Compatibility aliases for legacy imports
SOLEXS_ENERGY_RANGE_KV = SOLEXS_ENERGY_RANGE_KEV
HEL1OS_CDTE_RANGE_KV = HEL1OS_CDTE_RANGE_KEV
HEL1OS_CZT_RANGE_KV = HEL1OS_CZT_RANGE_KEV

HEL1OS_ENERGY_BANDS = {
    "band1": (5.0, 20.0),
    "band2": (20.0, 30.0),
    "band3": (30.0, 40.0),
    "band4": (40.0, 60.0),
    "total": (1.8, 90.0),
}

# GOES flare classification: peak 1-8 Angstrom flux thresholds (W/m^2)
GOES_CLASS_FLUX_THRESHOLDS = {
    "A": 1e-8,
    "B": 1e-7,
    "C": 1e-6,
    "M": 1e-5,
    "X": 1e-4,
}
GOES_CLASS_ORDER = ["A", "B", "C", "M", "X"]
GOES_SOLEXS_CROSS_CAL = {"slope": 0.95, "intercept": 0.0}

# Nowcast detector configuration defaults
NOWCAST_DEFAULTS = {
    "baseline_window_s": 600,        # 10-minute background window
    "cusum_threshold_sigma": 5.0,    # CUSUM alarm threshold (h)
    "cusum_slack_sigma": 1.0,        # CUSUM slack parameter (k)
    "peak_prominence_sigma": 3.0,
    "peak_min_height_sigma": 5.0,
    "fsm_consecutive_min": 4,        # GOES FSM: consecutive rising minutes
    "fsm_ratio": 1.4,                # GOES FSM: minute-4 / minute-1 flux ratio
}

# Forecast configuration defaults
FORECAST_DEFAULTS = {
    "horizons_min": [5, 15, 30, 60],
    "window_min": 30,
    "feature_smoothing_alpha": 0.3,
    "neupert_corr_window_s": 120,
    "calibration_method": "isotonic",
}

# Merge / synchronization defaults
MERGE_DEFAULTS = {
    "sync_grid_s": 1,
    "ltt_offset_solarorbiter_s": LTT_OFFSET_SOLAR_ORBITER_S,
    "ltt_offset_stereoa_s": LTT_OFFSET_STEREO_A_S,
    "ltt_offset_parker_s": LTT_OFFSET_PARKER_S,
    "gap_fill_max_s": 180,
    "fusion_method": "inverse_variance",
}

# Data path defaults
DATA_PATHS = {
    "raw": "data/raw",
    "processed": "data/processed",
    "cached": "data/cached",
    "models": "models",
    "logs": "logs",
}

# External API endpoints
GOES_SWPC_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json"
GOES_EVENTS_URL = (
    "https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json"
)
GOES_EVENTS_7DAY_URL = (
    "https://services.swpc.noaa.gov/json/goes/primary/xray-flares-7-day.json"
)
