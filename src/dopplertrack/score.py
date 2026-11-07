"""Compatibility alias; implementation: dopplertrack.components.scoring.trajectory_brightness."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.scoring.trajectory_brightness")
