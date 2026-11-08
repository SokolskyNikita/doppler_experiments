"""The Doppler curve of a straight pass: the received instantaneous frequency, over f0, of a source in straight-line
motion at constant speed (Ferguson & Quinn 1994 eqs. 14-15), parametrised by emission time around CPA."""
# old module: dopplertrack.components.detection.pass_shape
from __future__ import annotations

import numpy as np


# old name: pass_shape
def straight_pass_doppler_curve(v, d, c, span=400.0, n=161):
    """Reception-time offsets tau + r/c and Doppler ratios c / (c + dr/dtau) for a straight pass, at
    emission times tau relative to emission-time CPA (tau=0); core.propagation.ideal_curve is the
    same curve in reception time."""
    tau = np.linspace(-span, span, n)
    r = np.sqrt(d * d + (v * tau) ** 2)
    rr = v * v * tau / r
    return tau + r / c, c / (c + rr)
