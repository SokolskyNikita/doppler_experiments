"""Compatibility alias; implementation: dopplertrack.components.tracking.hmm."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.tracking.hmm")
