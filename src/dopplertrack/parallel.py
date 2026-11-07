"""Compatibility alias; implementation: dopplertrack.runtime.parallel."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.runtime.parallel")
