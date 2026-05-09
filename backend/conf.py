from pathlib import Path

BASE_DIR = Path(__file__).parent.parent / "data"
XHS_SERVER = "http://127.0.0.1:11901"
LOCAL_CHROME_PATH = ""

# 登录（扫码）必须有头模式，验证/发布可用无头模式
LOCAL_CHROME_HEADLESS = False
LOGIN_HEADLESS = False

DEBUG_MODE = True
