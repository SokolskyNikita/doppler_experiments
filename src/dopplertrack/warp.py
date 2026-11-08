"""Compatibility alias; implementation: dopplertrack.components.scoring.dedoppler_tone."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("dopplertrack.components.scoring.dedoppler_tone")
