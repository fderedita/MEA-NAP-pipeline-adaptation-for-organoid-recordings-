"""Stage 2.3 — spectral / aperiodic features.

Derive LFP by low-pass + downsample of raw (config: spectral.lfp_target_fs_hz);
Welch PSD; FOOOF/specparam -> aperiodic exponent + offset (primary),
oscillatory peak params if present; band power in low bands if oscillations
exist. Aperiodic exponent kept central as a maturation/E-I proxy.

Not yet implemented — gated behind Stage 1 validation (Checkpoint C).
"""
from __future__ import annotations


def derive_lfp(raw_signal, fs: float, config: dict):
    raise NotImplementedError


def compute_psd(lfp_signal, fs: float, config: dict):
    raise NotImplementedError


def fit_fooof(psd, freqs, config: dict) -> dict:
    raise NotImplementedError
