"""Compatibility alias; implementation: dopplertrack.components.spectrogram."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.spectrogram")
