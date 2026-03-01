"""
config.py — Backend Lambda Configuration & Structured Logging
=============================================================
Her log satırında şunlar bulunur:
  - timestamp, level, message
  - lambda_name: "backend"
  - request_id: Lambda invocation ID
  - user_id: DB'deki integer user ID
  - cognito_sub: Cognito UUID (kimlik doğrulama katmanı)
  - email: Kullanıcı e-postası (PII — yalnızca DEBUG/ERROR)
  - method: HTTP metodu (GET, POST, ...)
  - path: İstek yolu (/receipts, /dashboard, ...)
  - module: Hangi modül/route logu üretiyor
"""

import json
import logging
import os
import traceback

import boto3
from botocore.config import Config


# ══════════════════════════════════════════════════════════════════
#  Structured JSON Logger
# ══════════════════════════════════════════════════════════════════

class _StructuredFormatter(logging.Formatter):
    """
    Her log satırını CloudWatch'ta kolayca filtrelenebilir JSON'a dönüştürür.

    Context alanları LogRecord'a extra= ile eklenir:
        logger.info("msg", extra=log_ctx(user_id=42, path="/receipts"))
    """

    ALWAYS_FIELDS = (
        "lambda_name", "request_id", "user_id", "cognito_sub",
        "method", "path", "module",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "lambda_name": "backend",
            "message": record.getMessage(),
            "logger": record.name,
            "module": getattr(record, "module_name", record.module),
            # Context — sağlanmamışsa "-" (sorgu yaparken boş değer aramaktan kaçınır)
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "cognito_sub": getattr(record, "cognito_sub", "-"),
            "method": getattr(record, "method", "-"),
            "path": getattr(record, "path", "-"),
        }

        # E-posta gibi PII'yi yalnızca DEBUG & ERROR seviyelerinde ekle
        email = getattr(record, "email", None)
        if email and record.levelno in (logging.DEBUG, logging.ERROR):
            entry["email"] = email

        # Exception stack trace
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
            entry["exception_type"] = record.exc_info[0].__name__

        # Ekstra alanlar (extra= ile geçirilen ama yukarıda ele alınmayanlar)
        skip = {
            "msg", "args", "created", "filename", "funcName", "levelname",
            "levelno", "lineno", "module", "msecs", "name", "pathname",
            "process", "processName", "relativeCreated", "stack_info",
            "taskName", "thread", "threadName", "exc_info", "exc_text",
            "message",  # getMessage() ile zaten alındı
        } | set(self.ALWAYS_FIELDS) | {"module_name", "email"}

        for key, val in record.__dict__.items():
            if key not in skip and not key.startswith("_"):
                entry[key] = val

        return json.dumps(entry, ensure_ascii=False, default=str)


def _setup_logger() -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    formatter = _StructuredFormatter()
    if root.handlers:
        for h in root.handlers:
            h.setFormatter(formatter)
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    return root


logger = _setup_logger()


def log_ctx(**kwargs) -> dict:
    """
    Her fonksiyondan logger.info/warning/error çağrısının extra= parametresi olarak kullanılır.

    Örnek:
        logger.info("Receipts fetched", extra=log_ctx(
            request_id=request_id, user_id=user_id,
            method="GET", path="/receipts", module_name="receipts"
        ))
    """
    return kwargs


# ══════════════════════════════════════════════════════════════════
#  AWS & App Config
# ══════════════════════════════════════════════════════════════════

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID")
DB_HOST = os.environ.get("DB_HOST")
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_PORT = os.environ.get("DB_PORT", "5432")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
AI_LAMBDA_FUNCTION_NAME = os.environ.get("AI_LAMBDA_FUNCTION_NAME", "lambda_ai")
OCR_MAX_TOKENS = int(os.environ.get("OCR_MAX_TOKENS", "320"))
REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS", "30"))
AI_CACHE_TTL_SECONDS = int(os.environ.get("AI_CACHE_TTL_SECONDS", "21600"))
OCR_MAX_FILE_BYTES = int(os.environ.get("OCR_MAX_FILE_BYTES", "3145728"))
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
TOKEN_USE_ALLOWED = {
    x.strip()
    for x in os.environ.get("TOKEN_USE_ALLOWED", "access").split(",")
    if x.strip()
}
TITAN_EMBEDDING_MODEL_ID = os.environ.get("TITAN_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
RUN_DB_MIGRATIONS_ON_START = False

# ── AWS Clients ───────────────────────────────────────────────────
s3_client = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))
cognito = boto3.client("cognito-idp", region_name=AWS_REGION)
bedrock_runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)
ssm_client = boto3.client("ssm", region_name=AWS_REGION)
cw_client = boto3.client("cloudwatch", region_name=AWS_REGION)

# ── Pricing ───────────────────────────────────────────────────────
BEDROCK_INPUT_TOKEN_PRICE = float(os.environ.get("BEDROCK_INPUT_TOKEN_PRICE", "0.00000025"))
BEDROCK_OUTPUT_TOKEN_PRICE = float(os.environ.get("BEDROCK_OUTPUT_TOKEN_PRICE", "0.00000125"))

# ── Category Definitions ──────────────────────────────────────────
CATEGORIES = {
    1: "Market", 2: "Restoran", 3: "Kafe", 4: "Online Alışveriş",
    5: "Fatura", 6: "Konaklama", 7: "Ulaşım", 8: "Diğer",
    9: "Abonelik", 10: "Eğitim",
}

CATEGORY_KEYWORDS = {
    1: ["migros", "carrefour", "bim", "sok", "a101", "market", "bakkal", "tekel", "gida", "firin"],
    2: ["restaurant", "lokanta", "kebap", "burger", "pizza", "doner", "kofte", "pide", "lahmacun"],
    3: ["starbucks", "kahve", "cafe", "espresso", "latte", "cay", "tchibo", "arabica"],
    4: ["amazon", "trendyol", "hepsiburada", "getir", "n11", "boyner", "zara", "mango", "teknosa"],
    5: ["enerjisa", "igdas", "iski", "turkcell", "vodafone", "telekom", "fatura", "elektrik", "su", "internet", "netflix", "spotify"],
    6: ["otel", "hotel", "pansiyon", "konaklama", "airbnb", "tatil", "resort", "hostel"],
    7: ["taksi", "uber", "petrol", "shell", "opet", "bilet", "thy", "pegasus", "metro", "iett", "benzin", "motorin", "lpg"],
    8: ["eczane", "hastane", "saglik", "doktor", "klinik", "kuafor", "berber", "kirtasiye", "noter", "vergi", "diger"],
    9: ["spotify", "netflix", "youtube", "disney", "abonelik", "subscription", "premium"],
    10: ["okul", "egitim", "kurs", "kitap", "udemy", "kirtasiye", "college", "school"],
}

SUPPORTED_UPLOAD_TYPES = {
    "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/png": "png", "application/pdf": "pdf",
}

# ── Langfuse (lazy init) ──────────────────────────────────────────
langfuse_client = None


def get_langfuse():
    global langfuse_client
    if langfuse_client is None:
        try:
            from langfuse import Langfuse
            if LANGFUSE_PUBLIC_KEY and LANGFUSE_PUBLIC_KEY.startswith("ssm:"):
                pk_val = ssm_client.get_parameter(
                    Name=LANGFUSE_PUBLIC_KEY[4:], WithDecryption=True
                )["Parameter"]["Value"]
                sk_val = ssm_client.get_parameter(
                    Name=LANGFUSE_SECRET_KEY[4:], WithDecryption=True
                )["Parameter"]["Value"]
            else:
                pk_val = LANGFUSE_PUBLIC_KEY
                sk_val = LANGFUSE_SECRET_KEY
            if pk_val and sk_val:
                langfuse_client = Langfuse(public_key=pk_val, secret_key=sk_val, host=LANGFUSE_HOST)
            else:
                langfuse_client = False
        except Exception as exc:
            logger.error(
                "Langfuse init error",
                extra=log_ctx(module_name="config"),
                exc_info=True,
            )
            langfuse_client = False
    return langfuse_client if langfuse_client is not False else None
