"""Compatibility alias; implementation: dopplertrack.reporting.html."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.reporting.html")
