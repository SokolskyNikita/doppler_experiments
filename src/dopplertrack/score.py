"""Compatibility alias; implementation: dopplertrack.components.scoring.trajectory_score."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.scoring.trajectory_score")
