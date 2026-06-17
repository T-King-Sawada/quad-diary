"""アプリの基準ディレクトリとデータ／ログのパスを解決する。

Portable 方針：
* PyInstaller で固めた場合は .exe と同じフォルダを基準にする。
* スクリプト実行時はプロジェクトのルート（main.py のあるフォルダ）を基準にする。
"""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    """データ・設定・ログを置く基準フォルダ。"""
    if getattr(sys, "frozen", False):
        # PyInstaller でビルドされた .exe
        return Path(sys.executable).resolve().parent
    # スクリプト実行（app/ の 1 つ上 = プロジェクトルート）
    return Path(__file__).resolve().parent.parent


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
