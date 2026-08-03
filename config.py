import os
import json
import socks
from dotenv import load_dotenv
from typing import List, Dict, Optional, Any

load_dotenv()

# =====================================================
# ================= TELEGRAM ==========================
# =====================================================

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
CHANNELS = os.getenv("CHANNELS", "").split(",")
LOG_CHANNEL = os.getenv("LOG_CHANNEL", "")

# =====================================================
# ================= AI ================================
# =====================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

# =====================================================
# ================= ЛОГИКА ============================
# =====================================================

MIN_POST_LENGTH = int(os.getenv("MIN_POST_LENGTH", 40))
COMMENT_PROBABILITY = float(os.getenv("COMMENT_PROBABILITY", 0.8))
DIALOG_PROBABILITY = float(os.getenv("DIALOG_PROBABILITY", 0.2))
GIF_PROBABILITY = float(os.getenv("GIF_PROBABILITY", 0.2))
ROOT_COMMENTS_RANGE = (int(os.getenv("ROOT_COMMENTS_MIN", 1)), int(os.getenv("ROOT_COMMENTS_MAX", 3)))

POST_DELAY = (
    int(os.getenv("POST_DELAY_MIN", 10)),
    int(os.getenv("POST_DELAY_MAX", 20))
)

BETWEEN_COMMENTS_DELAY = (
    int(os.getenv("BETWEEN_COMMENTS_MIN", 50)),
    int(os.getenv("BETWEEN_COMMENTS_MAX", 70))
)

COMMENT_GENERATION_TRIES = int(os.getenv("COMMENT_GENERATION_TRIES", 8))
DIALOG_MESSAGES_RANGE = (2, 5)
DIALOG_DELAY_RANGE = (5, 11)
MAX_COMMENT_CHARS = 90

# =====================================================
# ================= АККАУНТЫ ==========================
# =====================================================

def parse_proxy(proxy_data: Optional[Dict[str, Any]]) -> Optional[tuple]:
    """Парсит прокси из словаря в формат для Telethon"""
    if not proxy_data:
        return None
    
    proxy_type = proxy_data.get("type", "socks5")
    
    if proxy_type == "socks5":
        proxy_type = socks.SOCKS5
    elif proxy_type == "socks4":
        proxy_type = socks.SOCKS4
    elif proxy_type == "http":
        proxy_type = socks.HTTP
    
    host = proxy_data.get("host")
    port = int(proxy_data.get("port", 1080))
    username = proxy_data.get("username")
    password = proxy_data.get("password")
    
    # Telethon ожидает именно такой формат для прокси с авторизацией
    if username and password:
        # Важно: порядок аргументов для Telethon
        return (proxy_type, host, port, username, password)
    return (proxy_type, host, port)

def load_accounts() -> List[Dict[str, Any]]:
    # Сначала пробуем загрузить из переменной окружения
    accounts_json = os.getenv("ACCOUNTS_JSON", "")
    
    if accounts_json:
        try:
            accounts = json.loads(accounts_json)
            for acc in accounts:
                if "proxy" in acc and acc["proxy"]:
                    acc["proxy"] = parse_proxy(acc["proxy"])
                else:
                    acc["proxy"] = None
                acc["role"] = acc.get("role", "commenter")
            return accounts
        except json.JSONDecodeError:
            pass
    
    # Если не получилось или переменная пуста, пробуем загрузить из файла
    accounts_file = os.getenv("ACCOUNTS_JSON_FILE", "")
    if accounts_file and os.path.exists(accounts_file):
        try:
            with open(accounts_file, "r", encoding="utf-8") as f:
                accounts = json.load(f)
                for acc in accounts:
                    if "proxy" in acc and acc["proxy"]:
                        acc["proxy"] = parse_proxy(acc["proxy"])
                    else:
                        acc["proxy"] = None
                    acc["role"] = acc.get("role", "commenter")
                return accounts
        except Exception as e:
            logging.error(f"Ошибка загрузки {accounts_file}: {e}")
    
    return []


ACCOUNTS = load_accounts()

# =====================================================
# ================= GIF ===============================
# =====================================================

GIF_FOLDER = "gifs"

# =====================================================
# ================= ВАЛИДАЦИЯ =========================
# =====================================================

def validate_config():
    errors = []
    
    if not API_ID:
        errors.append("API_ID не задан")
    if not API_HASH:
        errors.append("API_HASH не задан")
    if not CHANNELS or not CHANNELS[0]:
        errors.append("CHANNELS не задан")
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY не задан")
    if not ACCOUNTS:
        errors.append("Нет аккаунтов в ACCOUNTS_JSON")
    
    if errors:
        raise ValueError(f"Ошибки конфигурации:\n" + "\n".join(errors))

if not os.getenv("SKIP_VALIDATION"):
    validate_config()