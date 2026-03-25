"""JSON output serialization."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass


def to_json_envelope(data, schema_version: str = "1") -> str:
    """Wrap data in {ok, schema_version, data} envelope."""
    payload = _serialize(data)
    envelope = {
        "ok": True,
        "schema_version": schema_version,
        "data": payload,
    }
    return json.dumps(envelope, indent=2, default=str)


def error_json(code: str, message: str) -> str:
    return json.dumps({
        "ok": False,
        "error": {"code": code, "message": message},
    }, indent=2)


def _serialize(obj):
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return obj
    return obj


def is_piped() -> bool:
    return not sys.stdout.isatty()
