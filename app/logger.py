"""ログ設定。logs/app.log にローテーション付きで出力する。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import paths

_configured = False


def setup() -> None:
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        paths.logs_dir() / "app.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # コンソール（python main.py でデバッグ実行したとき用。pythonw では出力先なし）
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
