"""自動更新ロジックのテスト（ネットワークはモック）。"""

from __future__ import annotations

import requests

from app import updater


def test_parse_version():
    assert updater._parse_version("v1.2.0") == (1, 2, 0)
    assert updater._parse_version("1.10.3") == (1, 10, 3)
    assert updater._parse_version("v2") == (2,)


def test_is_newer():
    assert updater.is_newer("v1.3.0", "1.2.0") is True
    assert updater.is_newer("v1.2.1", "1.2.0") is True
    assert updater.is_newer("v1.2.0", "1.2.0") is False
    assert updater.is_newer("v1.1.0", "1.2.0") is False
    assert updater.is_newer("v1.10.0", "1.9.0") is True   # 数値比較（文字列比較でない）


class FakeResp:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


def test_check_for_update_found(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "1.2.0")
    payload = {
        "tag_name": "v1.3.0",
        "assets": [
            {"name": "other.txt", "browser_download_url": "x", "size": 1},
            {"name": "QuadDiary.exe", "browser_download_url": "https://dl/QuadDiary.exe", "size": 12345},
        ],
    }
    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: FakeResp(200, payload))
    info = updater.check_for_update()
    assert info is not None
    assert info.version == "v1.3.0"
    assert info.url == "https://dl/QuadDiary.exe"
    assert info.size == 12345


def test_download_rejects_incomplete(tmp_path, monkeypatch):
    """サイズ不一致（途中で切れたDL）は OSError で弾き、壊れたexeを入れない。"""

    class StreamResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def iter_content(self, n):
            yield b"only-a-few-bytes"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: StreamResp())
    dest = tmp_path / "QuadDiary.new.exe"
    try:
        updater._download("https://dl/QuadDiary.exe", dest, expected_size=99999)
        assert False, "should raise on size mismatch"
    except OSError:
        pass


def test_check_for_update_up_to_date(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "1.3.0")
    payload = {"tag_name": "v1.3.0", "assets": []}
    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: FakeResp(200, payload))
    assert updater.check_for_update() is None


def test_check_for_update_private_or_missing(monkeypatch):
    # 非公開/未公開なら 404 等 → None（例外を投げない）
    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: FakeResp(404, {}))
    assert updater.check_for_update() is None


def test_check_for_update_network_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(updater.requests, "get", boom)
    assert updater.check_for_update() is None   # 失敗時も None で握りつぶす


def test_apply_update_blocked_in_script_mode(monkeypatch):
    monkeypatch.setattr(updater, "can_self_update", lambda: False)
    try:
        updater.apply_update(updater.UpdateInfo(version="v1.3.0", url="x"))
        assert False, "should raise"
    except RuntimeError:
        pass
