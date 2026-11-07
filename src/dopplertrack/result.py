"""Compatibility alias; implementation: dopplertrack.runtime.records."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.runtime.records")
