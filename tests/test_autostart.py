"""自動起動の登録先修復ロジックのテスト（レジストリはモック）。"""

from __future__ import annotations

import sys

from app import autostart


def _frozen(monkeypatch, exe=r"C:\Users\u\AppData\Local\Programs\QuadDiary\QuadDiary.exe"):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", exe)


def test_needs_repair_when_registered_path_is_stale(monkeypatch):
    _frozen(monkeypatch)
    monkeypatch.setattr(
        autostart, "registered_command", lambda: r'"C:\Users\u\Favorites\QuadDiary.exe"'
    )
    assert autostart.needs_repair() is True


def test_no_repair_when_path_matches(monkeypatch):
    _frozen(monkeypatch)
    monkeypatch.setattr(autostart, "registered_command", lambda: autostart._command().upper())
    assert autostart.needs_repair() is False   # 大文字小文字の違いは同一扱い


def test_no_repair_when_not_registered(monkeypatch):
    _frozen(monkeypatch)
    monkeypatch.setattr(autostart, "registered_command", lambda: None)
    assert autostart.needs_repair() is False


def test_no_repair_in_script_mode(monkeypatch):
    """スクリプト実行は本番 exe の登録を奪わない。"""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(autostart, "registered_command", lambda: r'"C:\somewhere\QuadDiary.exe"')
    assert autostart.needs_repair() is False
