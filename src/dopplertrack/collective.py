"""Compatibility alias; implementation: dopplertrack.methods.collective.search."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.methods.collective.search")
