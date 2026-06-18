"""設定の2層構成・差分保存・トークン移行のテスト。"""

from __future__ import annotations

import json

from app import config as cfg


def _write_default(base, data):
    (base / "config.default.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def test_first_run_detection(isolated_paths, fake_secrets):
    assert cfg.is_first_run() is True
    cfg.save(cfg.managed_defaults())
    assert cfg.is_first_run() is False


def test_managed_defaults_merge_and_token_strip(isolated_paths, fake_secrets):
    _write_default(
        isolated_paths,
        {"reminder_time": "09:00", "confluence": {"space_id": "999", "api_token": "LEAK"}},
    )
    md = cfg.managed_defaults()
    assert md["reminder_time"] == "09:00"
    assert md["confluence"]["space_id"] == "999"
    assert md["confluence"]["api_token"] == ""   # ファイル由来トークンは無視


def test_save_writes_only_diff_without_token(isolated_paths, fake_secrets):
    _write_default(isolated_paths, {"confluence": {"space_id": "999"}})
    full = cfg.load()
    full["popup_mode"] = "force"
    full["confluence"]["enabled"] = True
    full["confluence"]["email"] = "me@x.com"
    full["confluence"]["space_id"] = "999"        # 管理者デフォルトと同じ
    full["confluence"]["api_token"] = "SECRET"
    cfg.save(full)

    on_disk = json.loads((isolated_paths / "config.json").read_text(encoding="utf-8"))
    assert "api_token" not in json.dumps(on_disk)      # トークンはファイルに書かない
    assert on_disk["popup_mode"] == "force"
    assert on_disk["confluence"]["email"] == "me@x.com"
    assert "space_id" not in on_disk.get("confluence", {})  # 既定と同値は書かない
    assert fake_secrets["t"] == "SECRET"               # トークンは store へ


def test_load_injects_token(isolated_paths, fake_secrets):
    fake_secrets["t"] = "TOK"
    c = cfg.load()
    assert c["confluence"]["api_token"] == "TOK"


def test_legacy_plaintext_token_migration(isolated_paths, fake_secrets):
    # 旧形式：config.json に平文トークン
    (isolated_paths / "config.json").write_text(
        json.dumps({"confluence": {"enabled": True, "email": "o@x.com", "api_token": "LEGACY"}}),
        encoding="utf-8",
    )
    c = cfg.load()
    assert c["confluence"]["api_token"] == "LEGACY"
    assert fake_secrets["t"] == "LEGACY"               # store へ移行
    on_disk = json.loads((isolated_paths / "config.json").read_text(encoding="utf-8"))
    assert "api_token" not in json.dumps(on_disk)      # ファイルからは削除


def test_corrupt_config_is_backed_up(isolated_paths, fake_secrets):
    (isolated_paths / "config.json").write_text("{ this is not json", encoding="utf-8")
    c = cfg.load()
    assert c["reminder_time"] == "18:30"               # 既定で復帰
    backups = list(isolated_paths.glob("config.broken.*.json"))
    assert len(backups) == 1
