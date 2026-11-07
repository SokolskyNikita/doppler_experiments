"""Compatibility alias; implementation: dopplertrack.data.coverage."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.data.coverage")
