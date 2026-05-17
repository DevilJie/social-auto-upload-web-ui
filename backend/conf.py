import os
import sys
from pathlib import Path

# 打包模式使用 SAU_DATA_DIR，开发模式回退到 repo/data
_data_dir = os.environ.get("SAU_DATA_DIR")
BASE_DIR = Path(_data_dir) if _data_dir else Path(__file__).parent.parent / "data"
XHS_SERVER = "http://127.0.0.1:11901"

# 自动检测 Chrome 路径
def _find_chrome():
    if sys.platform == "win32":
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    elif sys.platform == "darwin":
        p = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.isfile(p):
            return p
    else:
        import shutil
        found = shutil.which("google-chrome") or shutil.which("chromium-browser") or shutil.which("chromium")
        if found:
            return found
    return ""

LOCAL_CHROME_PATH = _find_chrome()

# 登录（扫码）必须有头模式，验证/发布可用无头模式
LOCAL_CHROME_HEADLESS = True
LOGIN_HEADLESS = False

DEBUG_MODE = True


def _load_proxy_url():
    """代理配置（占位，返回 None 表示不使用代理）"""
    return None
