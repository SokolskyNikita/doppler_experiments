"""Compatibility alias; implementation: dopplertrack.runtime.cache."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.runtime.cache")
