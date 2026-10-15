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


def is_reliable() -> bool:
    """この実行形態でレジストリ自動起動が確実に効くか。

    PyInstaller の .exe は通常プロセスなので確実。一方 Microsoft Store 版 Python
    （スクリプト実行）はレジストリ仮想化により本物の HKCU\\...\\Run に書けず、
    Windows ログオン時の自動起動が効かない。
    """
    if getattr(sys, "frozen", False):
        return True
    base = (sys.base_prefix or "").lower()
    return ("windowsapps" not in base) and ("pythonsoftwarefoundation" not in base)


def registered_command() -> str | None:
    """登録済みのコマンド文字列。未登録・取得失敗なら None。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return str(value)
    except FileNotFoundError:
        return None
    except OSError as e:
        log.warning("自動起動状態の取得に失敗: %s", e)
        return None


def is_enabled() -> bool:
    return registered_command() is not None


def needs_repair() -> bool:
    """登録先が今の exe と違うか（exe の移動・インストール版への移行後など）。

    frozen のときだけ True になり得る。スクリプト実行で登録を上書きして、
    本番の exe の自動起動を奪わないようにするため。
    """
    if not getattr(sys, "frozen", False):
        return False
    current = registered_command()
    return current is not None and current.lower() != _command().lower()


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
