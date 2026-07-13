"""Stage 2.3 — spectral / aperiodic features.

Derive LFP by low-pass + downsample of raw (config: spectral.lfp_target_fs_hz);
Welch PSD; FOOOF -> aperiodic exponent + offset (primary), oscillatory peak
count as a secondary indicator. Aperiodic exponent kept central as a
maturation/E-I proxy per the handoff.

Only computable for recordings with a raw ElectricalSeries -- DANDI:001603's
"sourced" subjects (HO5-8) have deposited Units only, no raw, so they will
not have spectral features (documented gap, not a bug -- see
build_feature_matrix.py).
"""
from __future__ import annotations

from math import gcd

import numpy as np
from fooof import FOOOF
from scipy.signal import butter, filtfilt, resample_poly, welch

from src.config import require


def derive_lfp(raw_signal, fs: float, config: dict) -> tuple[np.ndarray, float]:
    """Low-pass filter + downsample a raw voltage trace to LFP band/rate."""
    lowpass_hz = require(config, "spectral.lfp_lowpass_hz")
    target_fs = require(config, "spectral.lfp_target_fs_hz")

    nyq = fs / 2.0
    b, a = butter(4, lowpass_hz / nyq, btype="low")
    filtered = filtfilt(b, a, np.asarray(raw_signal, dtype=float))

    g = gcd(int(target_fs), int(fs))
    up, down = int(target_fs) // g, int(fs) // g
    lfp = resample_poly(filtered, up, down)
    return lfp, float(target_fs)


def compute_psd(lfp_signal: np.ndarray, fs: float, config: dict) -> tuple[np.ndarray, np.ndarray]:
    method = require(config, "spectral.psd_method")
    if method != "welch":
        raise ValueError(f"Unsupported spectral.psd_method: {method!r} (only 'welch' implemented)")
    nperseg = min(len(lfp_signal), int(fs * 2))  # 2s windows, or the whole signal if shorter
    freqs, psd = welch(lfp_signal, fs=fs, nperseg=nperseg)
    return freqs, psd


def fit_fooof(psd: np.ndarray, freqs: np.ndarray, config: dict) -> dict:
    """Fit FOOOF to one PSD, returning aperiodic exponent/offset + fit quality."""
    freq_range = require(config, "spectral.fooof.freq_range_hz")
    aperiodic_mode = require(config, "spectral.fooof.aperiodic_mode")

    fm = FOOOF(aperiodic_mode=aperiodic_mode, verbose=False)
    fm.fit(freqs, psd, tuple(freq_range))

    offset = float(fm.aperiodic_params_[0])
    exponent = float(fm.aperiodic_params_[-1])  # last param is always the exponent (fixed: [off,exp]; knee: [off,knee,exp])
    return {
        "aperiodic_offset": offset,
        "aperiodic_exponent": exponent,
        "n_peaks": int(len(fm.peak_params_)),
        "r_squared": float(fm.r_squared_),
        "fit_error": float(fm.error_),
    }


def compute_spectral_features_for_channel(raw_trace: np.ndarray, fs: float, config: dict) -> dict:
    """LFP derivation + PSD + FOOOF fit for one channel's raw trace."""
    lfp, lfp_fs = derive_lfp(raw_trace, fs, config)
    freqs, psd = compute_psd(lfp, lfp_fs, config)
    return fit_fooof(psd, freqs, config)


_SCALAR_FEATURE_KEYS = ["aperiodic_offset", "aperiodic_exponent", "n_peaks", "r_squared", "fit_error"]


def aggregate_spectral_features(per_channel_features: list[dict]) -> dict:
    """Recording-level summary: mean + dispersion (std) across channels.
    Channels where FOOOF failed to converge (r_squared very low / NaN) still
    contribute NaN, excluded via nanmean -- not silently dropped, matching
    the same NaN policy as spike_train.aggregate_spike_train_features.
    """
    result: dict = {"n_channels": len(per_channel_features)}
    for key in _SCALAR_FEATURE_KEYS:
        values = np.array([f.get(key, np.nan) for f in per_channel_features], dtype=float)
        result[f"{key}_mean"] = float(np.nanmean(values)) if len(values) else np.nan
        result[f"{key}_std"] = float(np.nanstd(values, ddof=1)) if np.sum(~np.isnan(values)) >= 2 else np.nan
    return result
