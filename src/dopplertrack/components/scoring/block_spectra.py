"""Short-time periodogram (spectrogram) of Hann blocks in dB (Kay 1998 §7.6.4 eq. 7.33; Harris 1978 for the Hann
window), and median spectral subtraction across frequency (Ramseier & Pieren 2023 eq. 11)."""
from __future__ import annotations

import numpy as np
import scipy.signal as ss
from scipy.ndimage import median_filter


def block_db(y: np.ndarray, sr: int, nperseg: int = 8192, hop: int = 2048, nfft: int | None = None,
             min_support: float = 1.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """dB power of Hann blocks of y, only blocks whose samples are all (min_support of them) inside
    the support. Returns (block centres in samples, frequencies, dB (B, F))."""
    nfft = nfft or nperseg
    w = ss.get_window("hann", nperseg)
    ok = np.isfinite(y)
    starts = np.arange(0, len(y) - nperseg + 1, hop)
    keep = [s for s in starts if ok[s:s + nperseg].mean() >= min_support]
    f = np.fft.rfftfreq(nfft, 1 / sr)
    if not keep:
        return np.array([]), f, np.zeros((0, len(f)))
    seg = np.stack([np.nan_to_num(y[s:s + nperseg]) * w for s in keep])
    P = np.abs(np.fft.rfft(seg, n=nfft, axis=1)) ** 2
    return np.array(keep) + nperseg / 2, f, 10 * np.log10(P + 1e-30)


# old name: across_frequency
def median_subtraction(db: np.ndarray, df: float, bg_hz: float = 10.0) -> np.ndarray:
    """Median spectral subtraction (Ramseier & Pieren eq. 11): each block's dB less its running median across
    frequency within +-bg_hz."""
    size = 2 * int(round(bg_hz / df)) + 1
    return db - median_filter(db, size=(1, size), mode="nearest")
