"""Compatibility alias; implementation: dopplertrack.data.trajectories."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.data.trajectories")
