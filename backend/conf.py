import os
from pathlib import Path

# 打包模式使用 SAU_DATA_DIR，开发模式回退到 repo/data
_data_dir = os.environ.get("SAU_DATA_DIR")
BASE_DIR = Path(_data_dir) if _data_dir else Path(__file__).parent.parent / "data"

# 确保 data/ 及所有必要子目录在启动时就存在
for _sub in ["db", "logs", "cookies", "cookiesFile", "uploads", "thumbnails", "upload_chunks"]:
    (BASE_DIR / _sub).mkdir(parents=True, exist_ok=True)

# 登录（扫码）必须有头模式，验证/发布可用无头模式
LOCAL_CHROME_HEADLESS = True
LOGIN_HEADLESS = False

# 反馈系统对接（密钥可暴露，不影响业务；用户已确认）
FEEDBACK_API_BASE_URL = os.environ.get('FEEDBACK_API_BASE_URL', 'https://feedback.cjxch.com')
FEEDBACK_APP_KEY = os.environ.get('FEEDBACK_APP_KEY', 'ak_6de413b0f08587a92df5314806920dbde2f4193b076f7431bacec657')
FEEDBACK_APP_SECRET = os.environ.get('FEEDBACK_APP_SECRET', 'sk_7aa34a39ad547ec2ccd0fc61f23825b197dbbd3bec565461615961f6ca7c113b52937e19c8f372d39c756ae0b5d9bd1f6514e5895e92d4e5')
FEEDBACK_API_TIMEOUT = int(os.environ.get('FEEDBACK_API_TIMEOUT', '10'))
