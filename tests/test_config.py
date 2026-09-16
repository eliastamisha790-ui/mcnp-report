from pathlib import Path

from mcnp_report.config import load_config, select_profile


def test_config_priority(monkeypatch, tmp_path):
    appdata = tmp_path / "appdata"
    user = appdata / "mcnp-report" / "config.toml"
    user.parent.mkdir(parents=True)
    user.write_text('[ai]\ndefault_profile="default"\n[ai.profiles.default]\nbase_url="https://user/v1"\nmodel="user"\n', encoding="utf-8")
    explicit = tmp_path / "explicit.toml"
    explicit.write_text('[ai.profiles.default]\nbase_url="https://explicit/v1"\nmodel="explicit"\n', encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("MCNP_REPORT_MODEL", "environment")
    config = load_config(str(explicit))
    profile = select_profile(config)
    assert profile.base_url == "https://explicit/v1"
    assert profile.model == "environment"
    assert config.loaded_files == [str(user), str(explicit.resolve())]
