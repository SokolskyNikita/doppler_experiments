"""Compatibility alias; implementation: dopplertrack.components.search.grid."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.search.grid")
