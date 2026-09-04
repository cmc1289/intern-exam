import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BANK_PATH = Path(os.environ.get("QUESTION_BANK_PATH", BASE_DIR / "question_bank.json"))
STATIC_DIR = Path(os.environ.get("STATIC_DIR", BASE_DIR))
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "exam_records.sqlite3"))

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get(
    "DEEPSEEK_BASE_URL",
    "https://api.deepseek.com/chat/completions",
)
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", "8000"))

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

# 管理后台登录（演示用）。密码未单独配置时回退到 ADMIN_TOKEN。
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "") or ADMIN_TOKEN or "admin123"
