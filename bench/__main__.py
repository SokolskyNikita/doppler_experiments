"""Compatibility entry point for the packaged evaluation harness."""
import importlib
import sys

_impl = importlib.import_module("dopplertrack.evaluation.cli")
if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
