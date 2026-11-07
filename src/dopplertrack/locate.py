"""Compatibility alias; implementation: dopplertrack.methods.grid_pair.runner."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.methods.grid_pair.runner")
