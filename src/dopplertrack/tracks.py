"""Compatibility alias; implementation: dopplertrack.components.detection.grid_scan."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.detection.grid_scan")
