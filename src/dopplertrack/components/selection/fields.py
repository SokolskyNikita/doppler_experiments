"""Read an event's field whether it is a fit (EventFit) or its dict (EventFit.to_dict, a saved detection)."""
from __future__ import annotations


def field(e, name: str):
    return e[name] if isinstance(e, dict) else getattr(e, name)
