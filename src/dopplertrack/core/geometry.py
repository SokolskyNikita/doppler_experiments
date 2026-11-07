"""Geodesy helpers: WGS-84 <-> ECEF <-> local East-North-Up (ENU)."""
from __future__ import annotations

import numpy as np

_A = 6378137.0
_F = 1 / 298.257223563
_E2 = _F * (2 - _F)


def lla_to_ecef(lat_deg, lon_deg, alt_m):
    lat = np.radians(lat_deg)
    lon = np.radians(lon_deg)
    s, c = np.sin(lat), np.cos(lat)
    n = _A / np.sqrt(1 - _E2 * s * s)
    x = (n + alt_m) * c * np.cos(lon)
    y = (n + alt_m) * c * np.sin(lon)
    z = (n * (1 - _E2) + alt_m) * s
    return np.stack([x, y, z], axis=-1)


def enu_rotation(lat0_deg, lon0_deg):
    lat, lon = np.radians(lat0_deg), np.radians(lon0_deg)
    sl, cl = np.sin(lat), np.cos(lat)
    so, co = np.sin(lon), np.cos(lon)
    return np.array([
        [-so, co, 0.0],
        [-sl * co, -sl * so, cl],
        [cl * co, cl * so, sl],
    ])


def lla_to_enu(lat_deg, lon_deg, alt_m, lat0_deg, lon0_deg, alt0_m=0.0):
    """Convert points to ENU metres relative to the origin. Broadcasts."""
    p = lla_to_ecef(np.asarray(lat_deg, float), np.asarray(lon_deg, float), np.asarray(alt_m, float))
    o = lla_to_ecef(lat0_deg, lon0_deg, alt0_m)
    return (p - o) @ enu_rotation(lat0_deg, lon0_deg).T


def enu_to_lla(e, n, u, lat0_deg, lon0_deg, alt0_m=0.0):
    r = enu_rotation(lat0_deg, lon0_deg)
    o = lla_to_ecef(lat0_deg, lon0_deg, alt0_m)
    xyz = np.stack([np.asarray(e, float), np.asarray(n, float), np.asarray(u, float)], -1) @ r + o
    x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - _E2))
    for _ in range(5):
        s = np.sin(lat)
        nn = _A / np.sqrt(1 - _E2 * s * s)
        alt = p / np.cos(lat) - nn
        lat = np.arctan2(z, p * (1 - _E2 * nn / (nn + alt)))
    return np.degrees(lat), np.degrees(lon), alt


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * np.arcsin(np.sqrt(a))
