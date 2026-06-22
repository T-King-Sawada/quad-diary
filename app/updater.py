"""GitHub リリースからの自動更新。

公開リポジトリの最新リリースを確認し、新しければ QuadDiary.exe をダウンロードして
自分自身を入れ替えて再起動する。実行中の exe は自分を上書きできないため、
「アプリ終了を待って入れ替え＆再起動する小バッチ」を生成して実行する。

注意：実際のダウンロードはリポジトリが公開されている前提（認証不要）。
スクリプト実行時（非 frozen）は自己更新できない。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from PySide6.QtCore import QObject, QThread, Signal

from . import __version__
from .logger import get_logger

log = get_logger(__name__)

REPO = "T-King-Sawada/quad-diary"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "QuadDiary.exe"
TIMEOUT = 20

CREATE_NO_WINDOW = 0x08000000


def _parse_version(v: str) -> tuple[int, ...]:
    """'v1.2.0' → (1, 2, 0)。数値以外は無視。"""
    v = (v or "").strip().lstrip("vV")
    out: list[int] = []
    for part in v.split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        out.append(int(digits) if digits else 0)
    return tuple(out)


def is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


@dataclass
class UpdateInfo:
    version: str
    url: str


def check_for_update() -> Optional[UpdateInfo]:
    """新しいリリースがあれば UpdateInfo を返す。無ければ／取得失敗なら None。"""
    try:
        r = requests.get(
            API_LATEST,
            headers={"Accept": "application/vnd.github+json"},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            log.info("更新チェック: HTTP %s（未公開/非公開の可能性）", r.status_code)
            return None
        data = r.json()
        tag = data.get("tag_name", "")
        if not tag or not is_newer(tag, __version__):
            return None
        for asset in data.get("assets", []):
            if asset.get("name") == ASSET_NAME:
                return UpdateInfo(version=tag, url=asset.get("browser_download_url", ""))
        log.warning("更新チェック: 資産 %s が見つかりません。", ASSET_NAME)
        return None
    except (requests.RequestException, ValueError) as e:
        log.info("更新チェック失敗: %s", e)
        return None


def can_self_update() -> bool:
    """frozen（.exe）でのみ自己更新可能。"""
    return bool(getattr(sys, "frozen", False))


def cleanup_old() -> None:
    """前回更新で残った .old.exe / _update.bat を起動時に掃除する。"""
    if not can_self_update():
        return
    exe = Path(sys.executable)
    for leftover in (exe.with_name(exe.stem + ".old.exe"), exe.with_name("_update.bat")):
        try:
            if leftover.exists():
                leftover.unlink()
        except OSError:
            pass  # まだ使用中等。次回再試行


def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)


def _swap_script(exe: Path, new: Path, pid: int) -> Path:
    """アプリ終了を待って exe を入れ替え再起動するバッチを生成。"""
    bat = exe.with_name("_update.bat")
    # chcp 65001 + UTF-8 で日本語パスにも対応
    content = (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        ":wait\r\n"
        f'tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul && '
        "(ping -n 2 127.0.0.1 >nul & goto wait)\r\n"
        f'move /y "{new}" "{exe}" >nul\r\n'
        f'start "" "{exe}"\r\n'
        'del "%~f0"\r\n'
    )
    bat.write_bytes(content.encode("utf-8"))
    return bat


def apply_update(info: UpdateInfo) -> None:
    """新 exe をダウンロードし、入れ替え用バッチを起動する。

    呼び出し側はこの後アプリを終了すること（バッチが終了を待って入れ替える）。
    """
    if not can_self_update():
        raise RuntimeError("スクリプト実行中は自動更新できません（.exe のみ）。")
    exe = Path(sys.executable)
    new = exe.with_name(exe.stem + ".new.exe")
    log.info("更新をダウンロード中: %s", info.version)
    _download(info.url, new)
    import os

    bat = _swap_script(exe, new, os.getpid())
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )
    log.info("更新スクリプトを起動しました。アプリを終了します。")


class UpdateChecker(QThread):
    """更新確認をバックグラウンドで行う。found / none / failed を通知。"""

    found = Signal(object)   # UpdateInfo
    none = Signal()

    def run(self) -> None:
        info = check_for_update()
        if info is not None:
            self.found.emit(info)
        else:
            self.none.emit()
