"""Unit tests for spectral.py using a synthetic 1/f^exponent signal with a
known ground-truth aperiodic exponent, to catch silent numeric errors.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest

from src.features.spectral import compute_psd, derive_lfp, fit_fooof

CONFIG = {
    "spectral": {
        "lfp_lowpass_hz": 300,
        "lfp_target_fs_hz": 1000,
        "psd_method": "welch",
        "fooof": {"freq_range_hz": [1, 100], "aperiodic_mode": "fixed"},
    }
}


def _synthetic_powerlaw_signal(exponent: float, fs: float, duration_s: float, seed: int = 0) -> np.ndarray:
    """White noise shaped to have power ~ 1/f^exponent (standard colored-noise
    synthesis: scale FFT amplitudes by 1/f^(exponent/2), inverse-FFT back)."""
    rng = np.random.default_rng(seed)
    n = int(fs * duration_s)
    white = rng.standard_normal(n)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    scale = np.ones_like(freqs)
    nonzero = freqs > 0
    scale[nonzero] = 1.0 / (freqs[nonzero] ** (exponent / 2.0))
    spectrum = np.fft.rfft(white) * scale
    signal = np.fft.irfft(spectrum, n=n)
    return signal / np.std(signal)


def test_fooof_recovers_known_aperiodic_exponent():
    """A synthetic signal built with a known 1/f^2 spectrum should yield a
    FOOOF-fit exponent close to 2.0 (loose tolerance -- this is a statistical
    fit on finite noisy data, not an exact reconstruction)."""
    true_exponent = 2.0
    fs = 1000.0
    signal = _synthetic_powerlaw_signal(true_exponent, fs=fs, duration_s=60.0, seed=42)

    freqs, psd = compute_psd(signal, fs, CONFIG)
    result = fit_fooof(psd, freqs, CONFIG)

    assert result["aperiodic_exponent"] == pytest.approx(true_exponent, abs=0.5)
    assert result["r_squared"] > 0.8


def test_derive_lfp_downsamples_to_target_rate():
    fs = 20000.0
    duration_s = 2.0
    raw = np.random.default_rng(0).standard_normal(int(fs * duration_s))
    lfp, lfp_fs = derive_lfp(raw, fs, CONFIG)
    assert lfp_fs == 1000.0
    assert lfp.shape[0] == pytest.approx(1000.0 * duration_s, abs=1)


def test_derive_lfp_attenuates_high_frequency_content():
    """A pure 5000Hz tone should be strongly attenuated by the 300Hz lowpass."""
    fs = 20000.0
    duration_s = 1.0
    t = np.arange(0, duration_s, 1 / fs)
    high_freq_tone = np.sin(2 * np.pi * 5000 * t)
    lfp, lfp_fs = derive_lfp(high_freq_tone, fs, CONFIG)
    # a 5kHz tone is far above the new Nyquist (500Hz) and the 300Hz cutoff --
    # after filtering the signal should be near-silent, not preserved at
    # full 1.0 amplitude.
    assert np.std(lfp) < 0.1
