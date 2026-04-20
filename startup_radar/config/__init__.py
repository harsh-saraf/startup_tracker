"""Config package — pydantic schema + loader. Single source of truth for config.yaml shape."""

from startup_radar.config.loader import ConfigError, load_config
from startup_radar.config.schema import (
    AppConfig,
    ConnectionsConfig,
    DeepDiveConfig,
    NetworkConfig,
    OutputConfig,
    SourcesConfig,
    TargetsConfig,
    UserConfig,
)
from startup_radar.config.secrets import Secrets, secrets

__all__ = [
    "AppConfig",
    "ConfigError",
    "ConnectionsConfig",
    "DeepDiveConfig",
    "NetworkConfig",
    "OutputConfig",
    "Secrets",
    "SourcesConfig",
    "TargetsConfig",
    "UserConfig",
    "load_config",
    "secrets",
]
