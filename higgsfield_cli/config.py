"""YAML config loader with defaults."""

from __future__ import annotations

from pathlib import Path

from .constants import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULTS = {
    "model": "nano-banana-pro",
    "resolution": "4k",
    "quality": "high",
    "aspect_ratio": "16:9",
    "batch_size": 4,
    "auto_download": False,
    "output_dir": ".",
}


def load_config() -> dict:
    """Load config with defaults."""
    config = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            import yaml
            user = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            config.update(user)
        except Exception:
            pass
    return config


def save_config(config: dict) -> None:
    """Save config to YAML."""
    import yaml
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Only save non-default values
    to_save = {k: v for k, v in config.items() if v != DEFAULTS.get(k)}
    CONFIG_FILE.write_text(yaml.dump(to_save, default_flow_style=False))


def get(key: str, default=None):
    """Get a single config value."""
    config = load_config()
    return config.get(key, default)
