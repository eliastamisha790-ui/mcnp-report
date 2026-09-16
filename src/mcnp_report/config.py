from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import tomllib
from typing import Any

from .errors import ConfigurationError


@dataclass
class AIProfile:
    name: str
    provider: str = "openai-compatible"
    base_url: str = ""
    endpoint: str = "chat_completions"
    model: str = ""
    api_key_env: str = "MCNP_REPORT_API_KEY"
    timeout_seconds: float = 60.0
    max_output_tokens: int = 1800
    temperature: float = 0.1
    json_mode: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    adapter_path: str = ""


@dataclass
class AppConfig:
    default_profile: str = "default"
    profiles: dict[str, AIProfile] = field(default_factory=dict)
    loaded_files: list[str] = field(default_factory=list)


def user_config_path() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return root / "mcnp-report" / "config.toml"


def _merge(target: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
    return target


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"无法读取配置 {path}：{exc}") from exc


def load_config(explicit: str | None = None) -> AppConfig:
    data: dict[str, Any] = {}
    loaded: list[str] = []
    user_path = user_config_path()
    if user_path.is_file():
        _merge(data, _read_toml(user_path)); loaded.append(str(user_path))
    if explicit:
        explicit_path = Path(explicit).expanduser().resolve()
        if not explicit_path.is_file():
            raise ConfigurationError(f"指定的配置文件不存在：{explicit_path}")
        _merge(data, _read_toml(explicit_path)); loaded.append(str(explicit_path))

    ai = data.get("ai", {})
    default_profile = str(ai.get("default_profile", "default"))
    profiles: dict[str, AIProfile] = {}
    for name, values in ai.get("profiles", {}).items():
        if not isinstance(values, dict):
            continue
        allowed = set(AIProfile.__dataclass_fields__) - {"name"}
        profiles[name] = AIProfile(name=name, **{k: v for k, v in values.items() if k in allowed})
    if not profiles:
        profiles["default"] = AIProfile(name="default")

    profile = profiles.get(default_profile)
    if profile:
        env_map = {
            "MCNP_REPORT_BASE_URL": "base_url", "MCNP_REPORT_MODEL": "model",
            "MCNP_REPORT_API_KEY_ENV": "api_key_env", "MCNP_REPORT_ENDPOINT": "endpoint",
        }
        for env_name, attr in env_map.items():
            if env_name in os.environ:
                setattr(profile, attr, os.environ[env_name])
    return AppConfig(default_profile, profiles, loaded)


def select_profile(config: AppConfig, name: str | None = None) -> AIProfile:
    selected = name or config.default_profile
    if selected not in config.profiles:
        raise ConfigurationError(f"AI 配置 profile 不存在：{selected}")
    return config.profiles[selected]
