"""保存先パス・旧レイアウト移行のテスト。"""

from __future__ import annotations

from app import paths


def test_migrate_legacy_copies_config_and_data(tmp_path, monkeypatch):
    src = tmp_path / "exe"
    dst = tmp_path / "appdata"
    src.mkdir()
    dst.mkdir()
    (src / "config.json").write_text('{"reminder_time":"09:00"}', encoding="utf-8")
    (src / "data").mkdir()
    (src / "data" / "diary_2026.jsonl").write_text("entry", encoding="utf-8")

    monkeypatch.setattr(paths, "_frozen", lambda: True)
    monkeypatch.setattr(paths, "exe_dir", lambda: src)
    monkeypatch.setattr(paths, "base_dir", lambda: dst)

    paths.migrate_legacy()

    assert (dst / "config.json").read_text(encoding="utf-8") == '{"reminder_time":"09:00"}'
    assert (dst / "data" / "diary_2026.jsonl").read_text(encoding="utf-8") == "entry"


def test_migrate_skips_when_dst_already_has_config(tmp_path, monkeypatch):
    src = tmp_path / "exe"
    dst = tmp_path / "appdata"
    src.mkdir()
    dst.mkdir()
    (src / "config.json").write_text('{"reminder_time":"09:00"}', encoding="utf-8")
    (dst / "config.json").write_text('{"reminder_time":"18:30"}', encoding="utf-8")

    monkeypatch.setattr(paths, "_frozen", lambda: True)
    monkeypatch.setattr(paths, "exe_dir", lambda: src)
    monkeypatch.setattr(paths, "base_dir", lambda: dst)

    paths.migrate_legacy()

    # 既存を上書きしない
    assert (dst / "config.json").read_text(encoding="utf-8") == '{"reminder_time":"18:30"}'


def test_migrate_noop_in_script_mode(tmp_path, monkeypatch):
    src = tmp_path / "exe"
    dst = tmp_path / "appdata"
    src.mkdir()
    dst.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(paths, "_frozen", lambda: False)  # スクリプト実行
    monkeypatch.setattr(paths, "exe_dir", lambda: src)
    monkeypatch.setattr(paths, "base_dir", lambda: dst)

    paths.migrate_legacy()
    assert not (dst / "config.json").exists()   # 非frozenでは移行しない
