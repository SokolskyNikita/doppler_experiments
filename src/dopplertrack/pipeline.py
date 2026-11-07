"""Compatibility alias; implementation: dopplertrack.methods.grid_pair.pipeline."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.methods.grid_pair.pipeline")
