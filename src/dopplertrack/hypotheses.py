"""Compatibility alias; implementation: dopplertrack.components.fitting.profile_hypotheses."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.fitting.profile_hypotheses")
