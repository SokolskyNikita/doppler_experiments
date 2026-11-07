"""Compatibility entry point for the packaged evaluation harness."""
import importlib
import sys

_impl = importlib.import_module("dopplertrack.evaluation.private")
sys.modules[__name__] = _impl
