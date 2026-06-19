"""Windows ログオン時の自動起動。HKCU\\...\\Run レジストリを使う。"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from .logger import get_logger

log = get_logger(__name__)

# 旧名のまま維持（リネーム後も既存の自動起動登録を壊さないため変更しない）
APP_NAME = "DailyDiary"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    """自動起動に登録するコマンド文字列。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # スクリプト実行時はコンソール無しの pythonw で main.py を起動
    pyw = Path(sys.executable).with_name("pythonw.exe")
    runtime = pyw if pyw.exists() else Path(sys.executable)
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{runtime}" "{main_py}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError as e:
        log.warning("自動起動状態の取得に失敗: %s", e)
        return False


def enable() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
        log.info("自動起動を有効化しました。")
        return True
    except OSError as e:
        log.error("自動起動の有効化に失敗: %s", e)
        return False


def disable() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
        log.info("自動起動を無効化しました。")
        return True
    except FileNotFoundError:
        return True  # もともと無い
    except OSError as e:
        log.error("自動起動の無効化に失敗: %s", e)
        return False


def apply(enabled: bool) -> bool:
    return enable() if enabled else disable()
