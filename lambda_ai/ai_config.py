"""
ai_config.py — AI Lambda Configuration & Structured Logging
============================================================
Her log satırında şunlar bulunur:
  - timestamp, level, message
  - lambda_name: "ai"
  - request_id: Lambda invocation ID
  - user_id: Calling user (backend'den payload ile gelir)
  - module_name: Hangi AI modülü logu üretiyor
  - Opsiyonel: elapsed_ms, period, tokens, cost_usd, step

CloudWatch Logs Insights sorgu örneği:
  fields @timestamp, message, user_id, request_id, elapsed_ms
  | filter lambda_name="ai" and user_id="42"
  | sort @timestamp desc
"""

import json
import logging
import os


# ══════════════════════════════════════════════════════════════════
#  Structured JSON Logger
# ══════════════════════════════════════════════════════════════════

class _AIStructuredFormatter(logging.Formatter):
    """
    AI Lambda için structured JSON log formatter.
    lambda_name="ai" ile backend loglarından ayrıştırılabilir.
    """

    CORE_FIELDS = {
        "lambda_name", "request_id", "user_id", "module_name",
        "period", "step", "elapsed_ms", "tokens_in", "tokens_out", "cost_usd",
    }

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "lambda_name": "ai",
            "message": record.getMessage(),
            "logger": record.name,
            # Context — sağlanmamışsa "-"
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "module_name": getattr(record, "module_name", record.module),
        }

        # Opsiyonel context alanları — sadece set edilmişse ekle
        for field in ("period", "step", "elapsed_ms", "tokens_in", "tokens_out", "cost_usd"):
            val = getattr(record, field, None)
            if val is not None:
                entry[field] = val

        # Exception stack trace
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
            entry["exception_type"] = record.exc_info[0].__name__

        # Formata özel olmayan ekstra alanlar
        skip = {
            "msg", "args", "created", "filename", "funcName", "levelname",
            "levelno", "lineno", "module", "msecs", "name", "pathname",
            "process", "processName", "relativeCreated", "stack_info",
            "taskName", "thread", "threadName", "exc_info", "exc_text",
            "message",
        } | self.CORE_FIELDS | {"lambda_name", "logger", "timestamp", "level"}

        for key, val in record.__dict__.items():
            if key not in skip and not key.startswith("_"):
                entry[key] = val

        return json.dumps(entry, ensure_ascii=False, default=str)


def _setup_ai_logger() -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    formatter = _AIStructuredFormatter()
    if root.handlers:
        for h in root.handlers:
            h.setFormatter(formatter)
    else:
        import sys
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root.addHandler(handler)
    return root


logger = _setup_ai_logger()


def log_ctx(**kwargs) -> dict:
    """
    Logger extra= parametresi için context dict oluşturur.

    Kullanım:
        logger.info("Step done", extra=log_ctx(
            request_id=rid, user_id=uid,
            module_name="forecast_engine",
            step="forecast", elapsed_ms=42
        ))
    """
    return kwargs


# ══════════════════════════════════════════════════════════════════
#  AI Lambda Config
# ══════════════════════════════════════════════════════════════════

import boto3

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "700"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.25"))
ANOMALY_Z_THRESHOLD = float(os.environ.get("ANOMALY_Z_THRESHOLD", "2.0"))
ANOMALY_IQR_FACTOR = float(os.environ.get("ANOMALY_IQR_FACTOR", "1.5"))
LLM_INPUT_TOKEN_PRICE = float(os.environ.get("LLM_INPUT_TOKEN_PRICE", "0.00000025"))
LLM_OUTPUT_TOKEN_PRICE = float(os.environ.get("LLM_OUTPUT_TOKEN_PRICE", "0.00000125"))

DEFAULT_CATEGORIES = {
    1: "Market", 2: "Restoran", 3: "Kafe", 4: "Online Alisveris",
    5: "Fatura", 6: "Konaklama", 7: "Ulasim", 8: "Diger",
}

# ── Lazy Bedrock Client ───────────────────────────────────────────
_bedrock_client = None


def get_bedrock_client():
    """Cold start optimizasyonu: ilk kullanımda init edilir."""
    global _bedrock_client
    if _bedrock_client is None:
        logger.info(
            "Initializing Bedrock client (lazy)",
            extra=log_ctx(module_name="ai_config"),
        )
        _bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _bedrock_client


# ── Lazy DB Connection (Async pattern için) ───────────────────────
import psycopg2
import psycopg2.extras

_db_conn = None
DB_HOST = os.environ.get("DB_HOST", "")
DB_NAME = os.environ.get("DB_NAME", "financeapp")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")


def get_db_connection():
    """
    AI Lambda DB bağlantısı.
    Yalnızca async pattern'de kullanılır —
    analiz sonucunu doğrudan DB'ye yazar.
    """
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        _db_conn = psycopg2.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            connect_timeout=5,
        )
    return _db_conn

