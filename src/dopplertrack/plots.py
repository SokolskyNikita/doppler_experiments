"""Compatibility alias; implementation: dopplertrack.reporting.plots."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.reporting.plots")
