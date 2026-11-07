"""Compatibility alias; implementation: dopplertrack.components.tracking.viterbi."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.tracking.viterbi")
