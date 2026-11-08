"""Compatibility alias; implementation: dopplertrack.components.tracking.hysteresis_viterbi."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.tracking.hysteresis_viterbi")
