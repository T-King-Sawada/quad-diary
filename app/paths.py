"""保存先パスの解決。

ユーザーデータ（config.json / data / logs）は散らからないよう 1 フォルダに集約する：
* exe 実行時 … `%APPDATA%\\QuadDiary\\`
* スクリプト実行時（開発）… プロジェクトルート（従来どおり・確認しやすい）

管理者デフォルト `config.default.json` は配布物に同梱する想定なので、
exe と同じフォルダ（開発時はプロジェクトルート）から読む。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "QuadDiary"


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def exe_dir() -> Path:
    """exe のあるフォルダ（開発時はプロジェクトルート）。config.default.json はここ。"""
    if _frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def base_dir() -> Path:
    """ユーザーデータ（config.json / data / logs）の基準フォルダ。"""
    if _frozen():
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        d = Path(appdata) / APP_NAME
    else:
        d = Path(__file__).resolve().parent.parent
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_dir() -> Path:
    d = base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = base_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return base_dir() / "config.json"


def default_config_path() -> Path:
    """管理者デフォルト。exe と同じフォルダ（配布物同梱）。"""
    return exe_dir() / "config.default.json"


def migrate_legacy() -> None:
    """旧レイアウト（exe 隣に config.json / data があった）から base_dir へ一度だけ移行。

    exe 実行時のみ。base_dir に既に config.json があれば何もしない。
    """
    if not _frozen():
        return
    dst = base_dir()
    if (dst / "config.json").exists():
        return  # 既に新レイアウト

    src = exe_dir()
    if src.resolve() == dst.resolve():
        return  # 同じ場所（念のため）

    try:
        legacy_cfg = src / "config.json"
        if legacy_cfg.exists():
            shutil.copy2(legacy_cfg, dst / "config.json")
        legacy_data = src / "data"
        if legacy_data.is_dir():
            shutil.copytree(legacy_data, dst / "data", dirs_exist_ok=True)
    except OSError:
        pass  # 移行失敗は致命的でない（次回起動時に再試行 or 新規開始）
