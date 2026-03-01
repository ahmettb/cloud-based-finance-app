import calendar
import decimal
import hashlib
import json
import re
from datetime import date, datetime

from config import (
    ALLOWED_ORIGIN, BEDROCK_INPUT_TOKEN_PRICE, BEDROCK_OUTPUT_TOKEN_PRICE,
    CATEGORIES, CATEGORY_KEYWORDS, S3_BUCKET_NAME, TITAN_EMBEDDING_MODEL_ID,
    bedrock_runtime, cw_client, logger, s3_client,
)


def _normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    replacements = {
        "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s",
        "Ç": "c", "ç": "c", "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u", "Ö": "o", "ö": "o",
    }
    for src, target in replacements.items():
        text = text.replace(src, target)
    return text.lower()


CATEGORY_NAME_TO_ID = {_normalize_text(name): cid for cid, name in CATEGORIES.items()}


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return str(value)


def api_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body, default=_json_default, ensure_ascii=False),
    }


def _safe_float(value, default=0.0):
    if value is None:
        return default
    try:
        out = float(value)
        if out != out or out in (float("inf"), float("-inf")):
            return default
        return out
    except (ValueError, TypeError):
        return default


def _coerce_bool(value, default=None):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _get_header(headers, key):
    if not headers:
        return ""
    if key in headers:
        return headers.get(key) or ""
    key_lower = key.lower()
    for h_key, h_val in headers.items():
        if (h_key or "").lower() == key_lower:
            return h_val or ""
    return ""


def _hash_token(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _parse_period(period):
    if not period or not isinstance(period, str):
        return datetime.now().strftime("%Y-%m")
    if re.match(r"^\d{4}-\d{2}$", period):
        return period
    return datetime.now().strftime("%Y-%m")


def _period_bounds(period):
    period = _parse_period(period)
    year = int(period[:4])
    month = int(period[5:7])
    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)
    return period, start_date, end_date


def _resolve_due_date_for_period(period, due_day):
    period, _, _ = _period_bounds(period)
    year = int(period[:4])
    month = int(period[5:7])
    last_day = calendar.monthrange(year, month)[1]
    due_day = max(1, min(int(due_day or 1), last_day))
    return date(year, month, due_day)


def _resolve_category_id(raw_category_id=None, raw_category_name=None, merchant_name=None):
    if raw_category_id is not None:
        try:
            cid = int(raw_category_id)
            if cid in CATEGORIES:
                return cid
        except Exception:
            pass
    normalized = _normalize_text(raw_category_name)
    if normalized:
        mapped = CATEGORY_NAME_TO_ID.get(normalized)
        if mapped:
            return mapped
        for cid, label in CATEGORIES.items():
            if _normalize_text(label) == normalized:
                return cid
        alias_map = {
            "ulasim": 7, "online alisveris": 4, "diger": 8,
            "saglik": 8, "eglence": 8, "giyim": 8, "teknoloji": 4,
        }
        if normalized in alias_map:
            return alias_map[normalized]
    return _determine_category(merchant_name or "")


def _determine_category(merchant_name, items=None, ai_suggested_id=None):
    if ai_suggested_id:
        try:
            candidate = int(ai_suggested_id)
            if candidate in CATEGORIES:
                return candidate
        except Exception:
            pass
    text = (merchant_name or "").lower()
    for cat_id, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return cat_id
    for item in (items or []):
        item_name = (item.get("name") or "").lower()
        if any(x in item_name for x in ["bira", "rakı", "viski", "vodka", "ekmek"]):
            return 1
        if any(x in item_name for x in ["iskender", "kuver", "servis ücreti", "kebap"]):
            return 2
        if any(x in item_name for x in ["benzin", "motorin", "dizel", "lpg"]):
            return 7
        if any(x in item_name for x in ["fatura", "aidat"]):
            return 5
    return 8


def _build_receipt_image_url(s3_key):
    if not s3_key or str(s3_key).startswith("manual/"):
        return None
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=300,
        )
    except Exception:
        return None


def _fix_date(date_str):
    if not date_str or not isinstance(date_str, str):
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    if mo < 1: mo = 1
    if mo > 12: mo = 12
    if d < 1: d = 1
    if d > 31: d = 31
    for _ in range(4):
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            d -= 1
            if d < 1:
                return None
    return None


def emit_bedrock_metrics(endpoint, input_tokens, output_tokens):
    try:
        cost = (input_tokens * BEDROCK_INPUT_TOKEN_PRICE) + (output_tokens * BEDROCK_OUTPUT_TOKEN_PRICE)
        cw_client.put_metric_data(
            Namespace="ParamNerede/Bedrock",
            MetricData=[
                {"MetricName": "InputTokens", "Value": input_tokens, "Unit": "Count", "Dimensions": [{"Name": "Endpoint", "Value": endpoint}]},
                {"MetricName": "OutputTokens", "Value": output_tokens, "Unit": "Count", "Dimensions": [{"Name": "Endpoint", "Value": endpoint}]},
                {"MetricName": "EstimatedCost", "Value": cost, "Unit": "None", "Dimensions": [{"Name": "Endpoint", "Value": endpoint}]},
            ]
        )
    except Exception as e:
        logger.warning(f"Failed to emit Bedrock metrics: {e}")


def get_text_embedding(text):
    if not text or not isinstance(text, str):
        return None
    try:
        payload = {"inputText": text[:8000], "dimensions": 1024, "normalize": True}
        resp = bedrock_runtime.invoke_model(
            modelId=TITAN_EMBEDDING_MODEL_ID,
            body=json.dumps(payload),
            accept="application/json",
            contentType="application/json"
        )
        resp_body = json.loads(resp["body"].read())
        emit_bedrock_metrics("embedding", resp_body.get("inputTextTokenCount", 0), 0)
        return resp_body.get("embedding")
    except Exception as exc:
        logger.error(f"Embedding generation failed: {exc}", exc_info=True)
        return None
