"""Compatibility alias; implementation: dopplertrack.data.terrain."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.data.terrain")
