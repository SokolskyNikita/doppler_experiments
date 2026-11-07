"""Compatibility alias; implementation: dopplertrack.commands.main."""
import importlib
import sys

_impl = importlib.import_module("dopplertrack.commands.main")
if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
