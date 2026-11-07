"""Compatibility alias; implementation: dopplertrack.core.atmosphere."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.core.atmosphere")
