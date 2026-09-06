from dataclasses import dataclass, field
from datetime import datetime
from enum import IntFlag, auto


class QCFlag(IntFlag):
    GOOD = 0
    FILLED = auto()
    INTERPOLATED = auto()
    SUSPECT = auto()
    BAD = auto()
    NEAR_SAA = auto()
    PARTICLE_HIT = auto()
    SATURATED = auto()


class Instrument(IntFlag):
    SOLEXS_SDD1 = auto()
    SOLEXS_SDD2 = auto()
    HEL1OS_CDTE = auto()
    HEL1OS_CZT = auto()
    GOES_XRS = auto()


@dataclass
class FluxSample:
    timestamp: datetime
    flux: float
    flux_sigma: float
    instrument: Instrument
    energy_band: str
    qc_flag: QCFlag = QCFlag.GOOD
    source_id: str = ""
    provenance: str = ""


@dataclass
class FlareEvent:
    start_time: datetime
    peak_time: datetime
    end_time: datetime
    peak_flux_solexs: float
    peak_flux_hel1os: float
    goes_class: str
    confidence: float
    instrument_flags: Instrument = field(default_factory=lambda: Instrument(0))
    neupert_verified: bool = False
    event_id: str = ""
    duration_s: float = 0.0


@dataclass
class FusedSample:
    timestamp: datetime
    soft_flux: float
    soft_sigma: float
    hard_flux: float
    hard_sigma: float
    hardness_ratio: float
    qc_flag: QCFlag = QCFlag.GOOD
    n_sources_soft: int = 0
    n_sources_hard: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "soft": self.soft_flux,
            "soft_sigma": self.soft_sigma,
            "hard": self.hard_flux,
            "hard_sigma": self.hard_sigma,
            "hardness_ratio": self.hardness_ratio,
            "n_sources_soft": self.n_sources_soft,
            "n_sources_hard": self.n_sources_hard,
        }


@dataclass
class ForecastOutput:
    timestamp: datetime
    probability: float
    lead_time_s: float
    horizon_min: int
    threshold_class: str
    calibrated_prob: float = 0.0
