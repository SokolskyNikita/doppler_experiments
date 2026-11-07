"""Compatibility entry point for the packaged evaluation harness."""
import importlib
import sys

_impl = importlib.import_module("dopplertrack.evaluation.report")
sys.modules[__name__] = _impl
