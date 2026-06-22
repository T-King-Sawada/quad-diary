"""pytest 共通設定とフィクスチャ。

- Qt はオフスクリーンで起動（GUIなしのCI/ヘッドレスでも動くように）。
- 実ファイル(config.json/data/logs)や Windows 資格情報マネージャーには触れないよう、
  paths と secrets_store をテスト用に差し替える。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# プロジェクトルートを import path に追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    """全テストで QApplication を確実に存在させる（QTimer/Widget 用）。"""
    return qapp


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """paths を一時ディレクトリに向け、実ファイルを触らせない。"""
    from app import paths

    monkeypatch.setattr(paths, "base_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "exe_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(paths, "default_config_path", lambda: tmp_path / "config.default.json")
    return tmp_path


@pytest.fixture
def fake_secrets(monkeypatch):
    """secrets_store をメモリ上の辞書に差し替える（資格情報マネージャーを触らない）。"""
    from app import secrets_store

    store: dict[str, str] = {}
    monkeypatch.setattr(secrets_store, "get_token", lambda: store.get("t", ""))
    monkeypatch.setattr(
        secrets_store, "set_token", lambda v: store.__setitem__("t", v) if v else store.pop("t", None)
    )
    monkeypatch.setattr(secrets_store, "clear_token", lambda: store.pop("t", None))
    return store
