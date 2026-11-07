"""Compatibility alias; implementation: dopplertrack.components.scoring.coherent."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.scoring.coherent")
