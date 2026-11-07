"""Compatibility alias; implementation: dopplertrack.core.propagation."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.core.propagation")
