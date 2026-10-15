"""GitHub リリースからの自動更新。

公開リポジトリの最新リリースを確認し、新しければ更新ファイルをダウンロードする。
実行中の exe は自分を上書きできないため、「アプリ終了を待って更新＆再起動する
小バッチ」を生成して実行する。

* QuadDiary-Setup.exe（Inno Setup）… 推奨。サイレントインストールで上書きし、
  インストーラ自身がアプリを再起動する。onedir（インストール版）はこれしか使えない
  （exe だけ差し替えると _internal と不整合になる）。
* QuadDiary.exe（旧 onefile）… onefile で動いていて Setup が無いリリースの場合のみ、
  従来どおり exe を入れ替える。

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
ASSET_NAME = "QuadDiary.exe"          # 旧 onefile 版
SETUP_ASSET_NAME = "QuadDiary-Setup.exe"
SETUP_ARGS = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"
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
    size: int = 0  # 期待ファイルサイズ（bytes）。0 は不明
    is_setup: bool = False  # True: インストーラ / False: 旧 onefile exe


def is_onefile() -> bool:
    """PyInstaller onefile で動いているか（onedir なら exe の隣に _internal がある）。"""
    if not getattr(sys, "frozen", False):
        return False
    return not (Path(sys.executable).parent / "_internal").is_dir()


def _pick_asset(assets: list) -> Optional[dict]:
    """Setup を優先。exe 単体の入れ替えは onefile のときだけ許す。"""
    by_name = {a.get("name"): a for a in assets}
    if SETUP_ASSET_NAME in by_name:
        return by_name[SETUP_ASSET_NAME]
    if ASSET_NAME in by_name and is_onefile():
        return by_name[ASSET_NAME]
    return None


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
        asset = _pick_asset(data.get("assets", []))
        if asset is None:
            log.warning("更新チェック: 使える資産（%s）が見つかりません。", SETUP_ASSET_NAME)
            return None
        return UpdateInfo(
            version=tag,
            url=asset.get("browser_download_url", ""),
            size=int(asset.get("size", 0) or 0),
            is_setup=asset.get("name") == SETUP_ASSET_NAME,
        )
    except (requests.RequestException, ValueError) as e:
        log.info("更新チェック失敗: %s", e)
        return None


def can_self_update() -> bool:
    """frozen（.exe）でのみ自己更新可能。"""
    return bool(getattr(sys, "frozen", False))


def cleanup_old() -> None:
    """前回更新で残った .old.exe / _update.bat / Setup を起動時に掃除する。"""
    if not can_self_update():
        return
    exe = Path(sys.executable)
    for leftover in (
        exe.with_name(exe.stem + ".old.exe"),
        exe.with_name("_update.bat"),
        exe.with_name(SETUP_ASSET_NAME),
    ):
        try:
            if leftover.exists():
                leftover.unlink()
        except OSError:
            pass  # まだ使用中等。次回再試行


def _download(url: str, dest: Path, expected_size: int = 0) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    # 不完全ダウンロード検出：壊れた exe を入れ替えてしまう事故を防ぐ
    if expected_size:
        actual = dest.stat().st_size
        if actual != expected_size:
            raise OSError(
                f"ダウンロードが不完全です（{actual}/{expected_size} bytes）。更新を中止します。"
            )


def _wait_lines(pid: int) -> str:
    # chcp 65001 + UTF-8 で日本語パスにも対応
    return (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        ":wait\r\n"
        f'tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul && '
        "(ping -n 2 127.0.0.1 >nul & goto wait)\r\n"
    )


def _swap_script(exe: Path, new: Path, pid: int) -> Path:
    """アプリ終了を待って exe を入れ替え再起動するバッチを生成（旧 onefile 用）。"""
    bat = exe.with_name("_update.bat")
    content = (
        _wait_lines(pid)
        + f'move /y "{new}" "{exe}" >nul\r\n'
        + f'start "" "{exe}"\r\n'
        + 'del "%~f0"\r\n'
    )
    bat.write_bytes(content.encode("utf-8"))
    return bat


def _setup_script(exe: Path, setup: Path, pid: int) -> Path:
    """アプリ終了を待ってインストーラをサイレント実行するバッチを生成。

    再起動はインストーラ（installer.iss の [Run] Check: WizardSilent）が行う。
    """
    bat = exe.with_name("_update.bat")
    content = (
        _wait_lines(pid)
        + f'"{setup}" {SETUP_ARGS}\r\n'
        + f'del "{setup}"\r\n'
        + 'del "%~f0"\r\n'
    )
    bat.write_bytes(content.encode("utf-8"))
    return bat


def apply_update(info: UpdateInfo) -> None:
    """更新ファイルをダウンロードし、更新用バッチを起動する。

    呼び出し側はこの後アプリを終了すること（バッチが終了を待って更新する）。
    """
    if not can_self_update():
        raise RuntimeError("スクリプト実行中は自動更新できません（.exe のみ）。")
    exe = Path(sys.executable)
    if not info.is_setup and not is_onefile():
        # onedir で exe だけ差し替えると _internal と不整合になり起動不能になる
        raise RuntimeError("このリリースにはインストーラが無いため自動更新できません。")
    new = exe.with_name(SETUP_ASSET_NAME if info.is_setup else exe.stem + ".new.exe")
    log.info("更新をダウンロード中: %s", info.version)
    try:
        _download(info.url, new, info.size)
    except Exception:
        # 不完全/失敗時は部分ファイルを消し、入れ替えはしない（古いexeを維持）
        try:
            if new.exists():
                new.unlink()
        except OSError:
            pass
        raise
    import os

    if info.is_setup:
        bat = _setup_script(exe, new, os.getpid())
    else:
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
