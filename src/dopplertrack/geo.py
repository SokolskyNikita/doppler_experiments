"""Compatibility alias; implementation: dopplertrack.core.geometry."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.core.geometry")
