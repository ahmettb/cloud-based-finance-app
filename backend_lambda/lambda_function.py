import base64
import calendar
import csv
import decimal
import hashlib
import io
import json
import logging
import os
import re
import time
import urllib.request
import uuid
from datetime import date, datetime, timedelta

import boto3
import psycopg2
from botocore.config import Config
from jose import jwk, jwt
from jose.utils import base64url_decode
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

# ============================================================
# CONFIGURATION
# ============================================================
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
TOKEN_USE_ALLOWED = {x.strip() for x in os.environ.get("TOKEN_USE_ALLOWED", "access").split(",") if x.strip()}
RUN_DB_MIGRATIONS_ON_START = os.environ.get("RUN_DB_MIGRATIONS_ON_START", "false").lower() == "true"

# ============================================================
# AWS CLIENTS
# ============================================================
s3_client = boto3.client("s3", region_name=AWS_REGION, config=Config(signature_version="s3v4"))
cognito = boto3.client("cognito-idp", region_name=AWS_REGION)
bedrock_runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION)
lambda_client = boto3.client("lambda", region_name=AWS_REGION)

# ============================================================
# GLOBAL STATE
# ============================================================
db_pool = None
jwks_cache = None
migration_checked = False

def _normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    replacements = {
        "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ü": "u", "ö": "o",
        "İ": "i", "Ş": "s", "Ç": "c", "Ğ": "g", "Ü": "u", "Ö": "o",
    }
    for src, target in replacements.items():
        text = text.replace(src, target)
    return text

CATEGORIES = {
    1: 'Market',
    2: 'Restoran',
    3: 'Kafe',
    4: 'Online Alışveriş',
    5: 'Fatura',
    6: 'Konaklama',
    7: 'Ulaşım',
    8: 'Diğer',
}

CATEGORY_NAME_TO_ID = {_normalize_text(name): cid for cid, name in CATEGORIES.items()}

CATEGORY_KEYWORDS = {
    1: ['migros', 'carrefour', 'bim', 'sok', 'a101', 'market', 'bakkal', 'tekel', 'gida', 'firin'],
    2: ['restaurant', 'lokanta', 'kebap', 'burger', 'pizza', 'doner', 'kofte', 'pide', 'lahmacun'],
    3: ['starbucks', 'kahve', 'cafe', 'espresso', 'latte', 'cay', 'tchibo', 'arabica'],
    4: ['amazon', 'trendyol', 'hepsiburada', 'getir', 'n11', 'boyner', 'zara', 'mango', 'teknosa'],
    5: ['enerjisa', 'igdas', 'iski', 'turkcell', 'vodafone', 'telekom', 'fatura', 'elektrik', 'su', 'internet', 'netflix', 'spotify'],
    6: ['otel', 'hotel', 'pansiyon', 'konaklama', 'airbnb', 'tatil', 'resort', 'hostel'],
    7: ['taksi', 'uber', 'petrol', 'shell', 'opet', 'bilet', 'thy', 'pegasus', 'metro', 'iett', 'benzin', 'motorin', 'lpg'],
    8: ['eczane', 'hastane', 'saglik', 'doktor', 'klinik', 'kuafor', 'berber', 'kirtasiye', 'noter', 'vergi', 'diger'],
}

SUPPORTED_UPLOAD_TYPES = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
}

def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return str(value)


def api_response(status_code, body):
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    return {
        "statusCode": status_code,
        "headers": headers,
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
            "ulasim": 7,
            "online alisveris": 4,
            "diger": 8,
            "saglik": 8,
            "eglence": 8,
            "giyim": 8,
            "teknoloji": 4,
        }
        if normalized in alias_map:
            return alias_map[normalized]

    return _determine_category(merchant_name or "")


def init_db_pool():
    global db_pool
    if db_pool is None:
        logger.info("Initializing DB pool")
        db_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=8,
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
            connect_timeout=8,
        )


def get_db_connection():
    if db_pool is None:
        init_db_pool()
    return db_pool.getconn()


def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)


def get_jwks():
    global jwks_cache
    if jwks_cache is None:
        if not COGNITO_USER_POOL_ID:
            raise RuntimeError("COGNITO_USER_POOL_ID is missing")
        keys_url = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        with urllib.request.urlopen(keys_url) as response:
            jwks_cache = json.loads(response.read())
    return jwks_cache


def verify_jwt(token):
    try:
        if not token or not isinstance(token, str):
            return None
        token = token.strip()

        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")
        if not kid:
            return None

        keys = get_jwks().get("keys", [])
        key = next((k for k in keys if k.get("kid") == kid), None)
        if not key:
            return None

        public_key = jwk.construct(key)
        message, encoded_signature = token.rsplit(".", 1)
        decoded_signature = base64url_decode(encoded_signature.encode("utf-8"))
        if not public_key.verify(message.encode("utf-8"), decoded_signature):
            return None

        claims = jwt.get_unverified_claims(token)
        exp = claims.get("exp", 0)
        if time.time() > exp:
            return None

        issuer = claims.get("iss", "")
        if COGNITO_USER_POOL_ID and COGNITO_USER_POOL_ID not in issuer:
            return None

        # Harden token validation scope.
        # Access token => client_id, ID token => aud. Accept either but require match.
        if COGNITO_CLIENT_ID:
            token_client = claims.get("client_id") or claims.get("aud")
            if token_client != COGNITO_CLIENT_ID:
                return None

        token_use = claims.get("token_use")
        if TOKEN_USE_ALLOWED and token_use not in TOKEN_USE_ALLOWED:
            return None

        return claims
    except Exception:
        return None


def maybe_run_migrations_once():
    """
    Optional runtime migration guard for non-prod environments.
    Disabled by default. For production, use deployment-time migrations.
    """
    global migration_checked
    if migration_checked or not RUN_DB_MIGRATIONS_ON_START:
        return
    try:
        ensure_tables_exist()
        migration_checked = True
    except Exception as exc:
        logger.error(f"Migration check failed: {exc}")

def _ensure_user_record(claims, fallback_full_name=None):
    conn = get_db_connection()
    try:
        sub = claims.get("sub")
        email = claims.get("email") or claims.get("username") or ""
        full_name = claims.get("name") or fallback_full_name
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO user_data (cognito_sub, email, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (cognito_sub)
                DO UPDATE SET email = EXCLUDED.email, full_name = COALESCE(EXCLUDED.full_name, user_data.full_name)
                RETURNING id, cognito_sub, email, full_name, created_at
                """,
                (sub, email, full_name),
            )
            user = cur.fetchone()
            conn.commit()
            return user
    finally:
        release_db_connection(conn)


def _save_refresh_token(user_id, refresh_token):
    if not refresh_token:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM refresh_tokens WHERE user_id=%s OR expires_at < NOW()", (user_id,))
            cur.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, _hash_token(refresh_token), datetime.utcnow() + timedelta(days=REFRESH_TOKEN_DAYS)),
            )
            conn.commit()
    except Exception as exc:
        logger.warning(f"refresh token save skipped: {exc}")
        conn.rollback()
    finally:
        release_db_connection(conn)


def handle_auth_register(body):
    email = (body or {}).get("email")
    password = (body or {}).get("password")
    full_name = (body or {}).get("full_name")

    if not email or not password:
        return api_response(400, {"error": "email and password are required"})
    if not COGNITO_CLIENT_ID:
        return api_response(500, {"error": "COGNITO_CLIENT_ID missing"})

    try:
        # Generate a UUID for the username to avoid "Username cannot be of email format" error
        # Cognito will still allow login via email alias if configured properly.
        username_uuid = str(uuid.uuid4())
        
        attributes = [
            {"Name": "email", "Value": email},
            {"Name": "name", "Value": full_name or email.split('@')[0]},
            {"Name": "nickname", "Value": full_name or email.split('@')[0]},
        ]
        logger.info(f"Registering user with attributes: {json.dumps(attributes)}")

        response = cognito.sign_up(
            ClientId=COGNITO_CLIENT_ID,
            Username=username_uuid,
            Password=password,
            UserAttributes=attributes,
        )
        return api_response(
            201,
            {
                "message": "Registration successful",
                "user_sub": response.get("UserSub"),
                "user_confirmed": response.get("UserConfirmed", False),
            },
        )
    except cognito.exceptions.UsernameExistsException:
        # Check if email exists (since uuid won't collide)
        return api_response(409, {"error": "User with this email already exists"})
    except Exception as exc:
        logger.error(f"register failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Registration failed"})


def handle_auth_login(body):
    email = (body or {}).get("email")
    password = (body or {}).get("password")
    if not email or not password:
        return api_response(400, {"error": "email and password are required"})
    if not COGNITO_CLIENT_ID:
        return api_response(500, {"error": "COGNITO_CLIENT_ID missing"})

    try:
        auth_resp = cognito.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            ClientId=COGNITO_CLIENT_ID,
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
        auth = auth_resp.get("AuthenticationResult", {})
        id_token = auth.get("IdToken")
        access_token = auth.get("AccessToken")
        refresh_token = auth.get("RefreshToken")

        if not id_token or not access_token:
            return api_response(401, {"error": "Authentication failed"})

        claims = jwt.get_unverified_claims(id_token)
        user = _ensure_user_record(claims, fallback_full_name=(body or {}).get("full_name"))
        _save_refresh_token(user["id"], refresh_token)

        return api_response(
            200,
            {
                "tokens": {
                    "access_token": access_token,
                    "id_token": id_token,
                    "refresh_token": refresh_token,
                    "expires_in": auth.get("ExpiresIn"),
                    "token_type": auth.get("TokenType", "Bearer"),
                },
                "user": {
                    "id": str(user["id"]),
                    "email": user.get("email"),
                    "full_name": user.get("full_name"),
                    "cognito_sub": user.get("cognito_sub"),
                },
            },
        )
    except cognito.exceptions.NotAuthorizedException:
        return api_response(401, {"error": "Invalid credentials"})
    except cognito.exceptions.UserNotConfirmedException:
        return api_response(403, {"error": "User is not confirmed"})
    except Exception as exc:
        logger.error(f"login failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Login failed"})


def handle_auth_refresh(body):
    refresh_token = (body or {}).get("refresh_token")
    if not refresh_token:
        return api_response(400, {"error": "refresh_token is required"})
    if not COGNITO_CLIENT_ID:
        return api_response(500, {"error": "COGNITO_CLIENT_ID missing"})

    try:
        auth_resp = cognito.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            ClientId=COGNITO_CLIENT_ID,
            AuthParameters={"REFRESH_TOKEN": refresh_token},
        )
        auth = auth_resp.get("AuthenticationResult", {})
        return api_response(
            200,
            {
                "tokens": {
                    "access_token": auth.get("AccessToken"),
                    "id_token": auth.get("IdToken"),
                    "refresh_token": refresh_token,
                    "expires_in": auth.get("ExpiresIn"),
                    "token_type": auth.get("TokenType", "Bearer"),
                }
            },
        )
    except cognito.exceptions.NotAuthorizedException:
        return api_response(401, {"error": "Invalid refresh token"})
    except Exception as exc:
        logger.error(f"refresh failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Token refresh failed"})


def handle_auth_me(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, cognito_sub, email, full_name, created_at FROM user_data WHERE id=%s",
                (user_id,),
            )
            user = cur.fetchone()
            if not user:
                return api_response(404, {"error": "User not found"})
            return api_response(200, {"user": user})
    finally:
        release_db_connection(conn)

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
    if not s3_key:
        return None
    if str(s3_key).startswith("manual/"):
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
    """
    Tries to parse YYYY-MM-DD. If day is out of range (e.g. Feb 30), clamps it to the last valid day of that month.
    Returns ISO format string or None if completely invalid.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    # Simple syntax check
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
    if not m:
        return None
        
    y, mo, d = map(int, m.groups())
    
    # Clamp month
    if mo < 1: mo = 1
    if mo > 12: mo = 12
    
    # Try to create date, reducing day if necessary (e.g. 31 -> 30 -> 29 -> 28)
    # We only Loop a few times because day is at most 31.
    if d < 1: d = 1
    if d > 31: d = 31
    
    for _ in range(4):
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            d -= 1
            if d < 1: return None
            
    return None


def handle_receipts_list(user_id, params):
    params = params or {}
    limit = min(max(int(params.get("limit", 50)), 1), 200)
    offset = max(int(params.get("offset", 0)), 0)

    filters = ["user_id = %s"]
    values = [user_id]

    status = params.get("status")
    if status:
        filters.append("status = %s")
        values.append(status)

    category_id = params.get("category_id")
    if category_id:
        try:
            filters.append("category_id = %s")
            values.append(int(category_id))
        except Exception:
            pass

    # Fix possible invalid dates (e.g. Feb 30) coming from frontend
    start_date = _fix_date(params.get("start_date"))
    if start_date:
        filters.append("receipt_date >= %s")
        values.append(start_date)

    end_date = _fix_date(params.get("end_date"))
    if end_date:
        filters.append("receipt_date <= %s")
        values.append(end_date)

    where_sql = " AND ".join(filters)

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, file_url, status, merchant_name, receipt_date, total_amount, category_id, created_at, updated_at
                FROM receipts
                WHERE {where_sql}
                ORDER BY COALESCE(receipt_date, created_at) DESC, created_at DESC
                LIMIT %s OFFSET %s
                """,
                values + [limit, offset],
            )
            rows = cur.fetchall()

            for row in rows:
                row["category"] = CATEGORIES.get(row.get("category_id"), "Diğer")

            cur.execute(f"SELECT COUNT(*) AS total FROM receipts WHERE {where_sql}", values)
            total = cur.fetchone()["total"]

        return api_response(
            200,
            {
                "data": rows,
                "pagination": {"limit": limit, "offset": offset, "total": total},
            },
        )
    finally:
        release_db_connection(conn)


def handle_receipt_detail(user_id, receipt_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, user_id, file_url, status, merchant_name, receipt_date, total_amount,
                       category_id, payment_method, description, created_at, updated_at
                FROM receipts
                WHERE id=%s AND user_id=%s
                """,
                (receipt_id, user_id),
            )
            receipt = cur.fetchone()
            if not receipt:
                return api_response(404, {"error": "Receipt not found"})

            cur.execute(
                """
                SELECT id, item_name, quantity, unit_price, total_price
                FROM receipt_items
                WHERE receipt_id=%s
                ORDER BY id ASC
                """,
                (receipt_id,),
            )
            items = cur.fetchall()

            receipt["items"] = items
            receipt["category"] = CATEGORIES.get(receipt.get("category_id"), "Diğer")
            receipt["image_url"] = _build_receipt_image_url(receipt.get("file_url"))
            if receipt["image_url"]:
                receipt["file_url"] = receipt["image_url"]
            elif str(receipt.get("file_url") or "").startswith("manual/"):
                receipt["file_url"] = None
            return api_response(200, receipt)
    finally:
        release_db_connection(conn)


def handle_receipt_update(user_id, receipt_id, body):
    body = body or {}
    allowed = {
        "merchant_name": body.get("merchant_name"),
        "total_amount": _safe_float(body.get("total_amount"), None),
        "receipt_date": body.get("receipt_date"),
        "category_id": body.get("category_id"),
        "payment_method": body.get("payment_method") or body.get("paymentMethod"),
        "description": body.get("description"),
    }

    updates = []
    values = []

    if allowed["merchant_name"] is not None:
        updates.append("merchant_name=%s")
        values.append(str(allowed["merchant_name"])[:255])

    if allowed["total_amount"] is not None:
        updates.append("total_amount=%s")
        values.append(allowed["total_amount"])

    if allowed["receipt_date"]:
        updates.append("receipt_date=%s")
        values.append(allowed["receipt_date"])

    if allowed["category_id"] is not None:
        try:
            cid = int(allowed["category_id"])
            if cid in CATEGORIES:
                updates.append("category_id=%s")
                values.append(cid)
        except Exception:
            pass

    if allowed.get("payment_method") is not None:
        updates.append("payment_method=%s")
        values.append(str(allowed["payment_method"])[:40])

    if allowed.get("description") is not None:
        updates.append("description=%s")
        values.append(str(allowed["description"])[:500])

    if not updates:
        return api_response(400, {"error": "No valid fields to update"})

    updates.append("updated_at=NOW()")
    values.extend([receipt_id, user_id])

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                UPDATE receipts
                SET {', '.join(updates)}
                WHERE id=%s AND user_id=%s
                RETURNING id, merchant_name, total_amount, receipt_date, category_id, status, updated_at
                """,
                values,
            )
            row = cur.fetchone()
            if not row:
                return api_response(404, {"error": "Receipt not found"})
            conn.commit()
            row["category"] = CATEGORIES.get(row.get("category_id"), "Diğer")
            return api_response(200, row)
    finally:
        release_db_connection(conn)


# ── Receipt Items CRUD ───────────────────────────────────────────
def handle_receipt_items(user_id, receipt_id, method, body, item_id=None):
    """Manage individual line items on a receipt."""
    body = body or {}
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Verify ownership
            cur.execute("SELECT id FROM receipts WHERE id=%s AND user_id=%s", (receipt_id, user_id))
            if not cur.fetchone():
                return api_response(404, {"error": "Receipt not found"})

            if method == "POST":
                item_name = str(body.get("item_name") or "").strip()
                quantity = max(int(_safe_float(body.get("quantity"), 1)), 1)
                unit_price = _safe_float(body.get("unit_price"), 0.0)
                total_price = _safe_float(body.get("total_price"), None) or round(unit_price * quantity, 2)
                if not item_name:
                    return api_response(400, {"error": "item_name is required"})
                cur.execute(
                    """
                    INSERT INTO receipt_items (receipt_id, item_name, quantity, unit_price, total_price)
                    VALUES (%s,%s,%s,%s,%s)
                    RETURNING id, receipt_id, item_name, quantity, unit_price, total_price
                    """,
                    (receipt_id, item_name[:255], quantity, unit_price, total_price),
                )
                created = cur.fetchone()
                conn.commit()
                return api_response(201, created)

            if method in {"PUT", "PATCH"} and item_id:
                sets, vals = [], []
                if body.get("item_name") is not None:
                    sets.append("item_name=%s")
                    vals.append(str(body["item_name"])[:255])
                if body.get("quantity") is not None:
                    sets.append("quantity=%s")
                    vals.append(max(int(_safe_float(body["quantity"], 1)), 1))
                if body.get("unit_price") is not None:
                    sets.append("unit_price=%s")
                    vals.append(_safe_float(body["unit_price"], 0.0))
                if body.get("total_price") is not None:
                    sets.append("total_price=%s")
                    vals.append(_safe_float(body["total_price"], 0.0))
                if not sets:
                    return api_response(400, {"error": "No valid fields"})
                vals.extend([item_id, receipt_id])
                cur.execute(
                    f"""
                    UPDATE receipt_items SET {', '.join(sets)}
                    WHERE id=%s AND receipt_id=%s
                    RETURNING id, receipt_id, item_name, quantity, unit_price, total_price
                    """,
                    vals,
                )
                updated = cur.fetchone()
                if not updated:
                    return api_response(404, {"error": "Item not found"})
                conn.commit()
                return api_response(200, updated)

            if method == "DELETE" and item_id:
                cur.execute("DELETE FROM receipt_items WHERE id=%s AND receipt_id=%s RETURNING id", (item_id, receipt_id))
                if not cur.fetchone():
                    return api_response(404, {"error": "Item not found"})
                conn.commit()
                return api_response(200, {"deleted": True})

            return api_response(405, {"error": "Method not allowed"})
    finally:
        release_db_connection(conn)


# ── AI Action Apply (one-click) ─────────────────────────────────
def handle_ai_action_apply(user_id, action_id, body):
    """Execute a concrete action tied to an AI recommendation.
    Supported action types:
      - set_budget: {category_name, amount}
      - create_goal: {title, target_amount, ...}
    Marks the action as done after successful execution.
    """
    body = body or {}
    action_type = str(body.get("action_type") or "").strip()

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Verify action belongs to user
            cur.execute(
                "SELECT id, title, status FROM ai_action_items WHERE id=%s AND user_id=%s",
                (action_id, user_id),
            )
            action = cur.fetchone()
            if not action:
                return api_response(404, {"error": "Action not found"})

            result = None

            if action_type == "set_budget":
                category_name = str(body.get("category_name") or "").strip()
                amount = _safe_float(body.get("amount"), None)
                if not category_name or amount is None or amount <= 0:
                    return api_response(400, {"error": "category_name and valid amount required"})
                cur.execute(
                    """
                    INSERT INTO budgets (user_id, category_name, amount)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, category_name) DO UPDATE SET amount=EXCLUDED.amount, updated_at=NOW()
                    RETURNING id, category_name, amount
                    """,
                    (user_id, category_name[:100], amount),
                )
                result = {"type": "budget_set", "data": cur.fetchone()}

            elif action_type == "create_goal":
                title = str(body.get("title") or "").strip()
                target_amount = _safe_float(body.get("target_amount"), None)
                if not title or target_amount is None or target_amount <= 0:
                    return api_response(400, {"error": "title and valid target_amount required"})
                cur.execute(
                    """
                    INSERT INTO financial_goals (user_id, title, target_amount, metric_type, status)
                    VALUES (%s, %s, %s, %s, 'active')
                    RETURNING id, title, target_amount, status
                    """,
                    (user_id, title[:120], target_amount, body.get("metric_type", "savings")),
                )
                result = {"type": "goal_created", "data": cur.fetchone()}

            elif action_type == "cancel_subscription":
                sub_name = str(body.get("subscription_name") or "").strip()
                if not sub_name:
                    return api_response(400, {"error": "subscription_name required"})
                cur.execute(
                    "DELETE FROM subscriptions WHERE user_id=%s AND LOWER(name) = LOWER(%s) RETURNING id, name",
                    (user_id, sub_name),
                )
                deleted = cur.fetchone()
                result = {"type": "subscription_cancelled", "data": deleted}

            else:
                return api_response(400, {"error": f"Unknown action_type: {action_type}. Supported: set_budget, create_goal, cancel_subscription"})

            # Mark action as done
            cur.execute(
                """
                UPDATE ai_action_items SET status='done', done_at=NOW(), updated_at=NOW()
                WHERE id=%s AND user_id=%s
                """,
                (action_id, user_id),
            )
            conn.commit()
            return api_response(200, {"applied": True, "result": result})
    finally:
        release_db_connection(conn)


def handle_receipt_process(user_id, receipt_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, file_url, status FROM receipts WHERE id=%s AND user_id=%s",
                (receipt_id, user_id),
            )
            receipt = cur.fetchone()
            if not receipt:
                return api_response(404, {"error": "Receipt not found"})
            if receipt["status"] == "completed":
                return api_response(200, {"message": "Receipt already processed"})

            cur.execute("UPDATE receipts SET status='processing', updated_at=NOW() WHERE id=%s", (receipt_id,))
            conn.commit()

            try:
                s3_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=receipt["file_url"])
                file_bytes = s3_obj["Body"].read()
            except Exception as exc:
                cur.execute("UPDATE receipts SET status='failed', updated_at=NOW() WHERE id=%s", (receipt_id,))
                conn.commit()
                return api_response(500, {"error": f"File read failed: {exc}"})

            if len(file_bytes) > OCR_MAX_FILE_BYTES:
                cur.execute("UPDATE receipts SET status='failed', updated_at=NOW() WHERE id=%s", (receipt_id,))
                conn.commit()
                return api_response(
                    413,
                    {
                        "error": "File too large for OCR",
                        "max_bytes": OCR_MAX_FILE_BYTES,
                        "current_bytes": len(file_bytes),
                    },
                )

            if receipt["file_url"].lower().endswith(".pdf"):
                media_type = "application/pdf"
            elif receipt["file_url"].lower().endswith(".png"):
                media_type = "image/png"
            else:
                media_type = "image/jpeg"

            image_b64 = base64.b64encode(file_bytes).decode("utf-8")
            system_prompt = "You are a financial AI assistant. Analyze the receipt image and extraction structured data. Output ONLY raw JSON. No markdown formatting, no code blocks, no conversational text."
            
            user_prompt = (
                "Extract JSON only with fields: merchant_name,total_amount,receipt_date(YYYY-MM-DD),"
                "items[{name,price}],currency(default TRY),category_id(1-8). "
                "Categories:1 Market,2 Restoran,3 Kafe,4 Eğlence,5 Fatura,6 Giyim,7 Ulaşım,8 Diğer. "
                "No markdown or extra text."
            )

            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1500,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": user_prompt},
                        ],
                    }
                ],
            }

            raw_text = "{}"
            try:
                # Invoke Bedrock - Claude 3
                resp = bedrock_runtime.invoke_model(
                    modelId=BEDROCK_MODEL_ID, 
                    body=json.dumps(payload)
                )
                resp_body = json.loads(resp["body"].read())
                
                # Extract text content from response
                content_block = resp_body.get("content", [])
                if content_block and isinstance(content_block, list):
                    raw_text = content_block[0].get("text", "{}")
                else:
                    logger.error(f"Unexpected Bedrock response format: {resp_body}")
                    
            except Exception as exc:
                logger.error(f"Bedrock OCR invoke failed: {exc}", exc_info=True)
                # If bedrock fails, we can't do anything
                cur.execute("UPDATE receipts SET status='failed', last_error=%s, updated_at=NOW() WHERE id=%s", (str(exc), receipt_id,))
                conn.commit()
                return api_response(500, {"error": "AI Service error"})

            ocr_data = {}
            try:
                # 1. Clean Markdown Code Blocks
                clean_text = raw_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                
                clean_text = clean_text.strip()

                # 2. Extract JSON with Regex (Greedy)
                # Find the first { and the last }
                start_idx = clean_text.find('{')
                end_idx = clean_text.rfind('}')

                if start_idx != -1 and end_idx != -1:
                    json_str = clean_text[start_idx : end_idx + 1]
                    ocr_data = json.loads(json_str)
                else:
                    # Fallback to direct load
                   ocr_data = json.loads(clean_text)

            except Exception as parse_exc:
                logger.error(f"OCR JSON Parse Failed. Raw text was: {raw_text[:1000]}")
                # Don't fail immediately, maybe manual entry is needed
                pass

            if not ocr_data:
                # If we couldn't get JSON, mark as failed but keep raw text in logs
                cur.execute("UPDATE receipts SET status='failed', updated_at=NOW() WHERE id=%s", (receipt_id,))
                conn.commit()
                return api_response(422, {"error": "OCR parse failed", "raw_response": raw_text[:500]})

            merchant = str(ocr_data.get("merchant_name") or "Bilinmiyor")[:255]
            amount = _safe_float(ocr_data.get("total_amount"), 0.0)
            r_date = ocr_data.get("receipt_date") or date.today().isoformat()
            items = ocr_data.get("items") or []
            currency = str(ocr_data.get("currency") or "TRY")[:10]
            category_id = _determine_category(merchant, items=items, ai_suggested_id=ocr_data.get("category_id"))

            cur.execute(
                """
                UPDATE receipts
                SET merchant_name=%s, total_amount=%s, receipt_date=%s, category_id=%s,
                    currency=%s, status='completed', updated_at=NOW()
                WHERE id=%s
                """,
                (merchant, amount, r_date, category_id, currency, receipt_id),
            )

            cur.execute("DELETE FROM receipt_items WHERE receipt_id=%s", (receipt_id,))
            for item in items[:30]:
                cur.execute(
                    "INSERT INTO receipt_items (receipt_id, item_name, total_price) VALUES (%s,%s,%s)",
                    (receipt_id, str(item.get("name") or "")[:255], _safe_float(item.get("price"))),
                )

            conn.commit()
            return api_response(
                200,
                {
                    "receipt_id": receipt_id,
                    "status": "completed",
                    "merchant_name": merchant,
                    "total_amount": amount,
                    "receipt_date": r_date,
                    "category_id": category_id,
                    "category_name": CATEGORIES.get(category_id, "Diğer"),
                    "items_count": min(len(items), 30),
                    "currency": currency,
                    "ocr_data": ocr_data,
                },
            )
    except Exception as exc:
        logger.error(f"receipt process failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Process failed"})
    finally:
        release_db_connection(conn)


def handle_receipt_delete(user_id, receipt_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM receipts WHERE id=%s AND user_id=%s RETURNING file_url",
                (receipt_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                return api_response(404, {"error": "Receipt not found"})
            conn.commit()

            try:
                s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=row[0])
            except Exception:
                pass
            return api_response(200, {"message": "Deleted"})
    finally:
        release_db_connection(conn)


def handle_upload_init(user_id, body):
    body = body or {}
    filename = body.get("filename")
    ctype = body.get("content_type")
    if not filename or not ctype:
        return api_response(400, {"error": "filename and content_type are required"})

    ext = SUPPORTED_UPLOAD_TYPES.get(ctype)
    if not ext:
        return api_response(400, {"error": "Unsupported content_type"})

    rid = str(uuid.uuid4())
    key = f"users/{user_id}/receipts/{rid}.{ext}"

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO receipts (id, user_id, file_url, status) VALUES (%s,%s,%s,'pending')",
                (rid, user_id, key),
            )
            conn.commit()
    finally:
        release_db_connection(conn)

    upload_url = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": S3_BUCKET_NAME, "Key": key, "ContentType": ctype},
        ExpiresIn=600,
    )
    return api_response(200, {"upload_url": upload_url, "receipt_id": rid, "s3_key": key})


def handle_manual_receipt_create(user_id, body):
    body = body or {}
    merchant_name = str(body.get("merchant_name") or "").strip()
    total_amount = _safe_float(body.get("total_amount"), None)
    receipt_date = body.get("receipt_date") or date.today().isoformat()
    currency = str(body.get("currency") or "TRY").strip().upper()[:10]
    payment_method = str(body.get("payment_method") or body.get("paymentMethod") or "").strip()[:40] or None
    description = str(body.get("description") or "").strip()[:500] or None
    category_id = _resolve_category_id(
        raw_category_id=body.get("category_id"),
        raw_category_name=body.get("category_name"),
        merchant_name=merchant_name,
    )

    if not merchant_name:
        return api_response(400, {"error": "merchant_name is required"})
    if total_amount is None or total_amount <= 0:
        return api_response(400, {"error": "total_amount must be greater than 0"})

    try:
        datetime.strptime(str(receipt_date), "%Y-%m-%d")
    except Exception:
        return api_response(400, {"error": "receipt_date must be YYYY-MM-DD"})

    rid = str(uuid.uuid4())
    manual_key = f"manual/{user_id}/{rid}.json"

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO receipts (id, user_id, file_url, status, merchant_name, receipt_date, total_amount, category_id, currency, payment_method, description)
                VALUES (%s,%s,%s,'completed',%s,%s,%s,%s,%s,%s,%s)
                RETURNING id, merchant_name, receipt_date, total_amount, category_id, status, payment_method, description, created_at, updated_at
                """,
                (rid, user_id, manual_key, merchant_name[:255], receipt_date, total_amount, category_id, currency, payment_method, description),
            )
            created = cur.fetchone()
            conn.commit()

            created["category"] = CATEGORIES.get(category_id, "Diğer")
            created["source"] = "manual"
            return api_response(201, created)
    finally:
        release_db_connection(conn)


def handle_reports_summary(user_id, params):
    params = params or {}
    try:
        months = int(params.get("months", 12))
    except Exception:
        months = 12
    months = max(1, min(24, months))

    today = datetime.utcnow().date()
    period_start = (today.replace(day=1) - timedelta(days=32 * (months - 1))).replace(day=1)

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT TO_CHAR(DATE_TRUNC('month', receipt_date), 'YYYY-MM') AS month,
                       COUNT(*) AS receipt_count,
                       COALESCE(SUM(total_amount),0) AS total_expense,
                       COALESCE(AVG(total_amount),0) AS avg_expense
                FROM receipts
                WHERE user_id=%s AND status='completed' AND receipt_date >= %s
                GROUP BY 1
                ORDER BY 1 DESC
                """,
                (user_id, period_start),
            )
            monthly_rows = cur.fetchall()

            cur.execute(
                """
                SELECT TO_CHAR(DATE_TRUNC('month', receipt_date), 'YYYY-MM') AS month,
                       category_id,
                       COALESCE(SUM(total_amount),0) AS total
                FROM receipts
                WHERE user_id=%s AND status='completed' AND receipt_date >= %s
                GROUP BY 1,2
                ORDER BY 1 DESC, total DESC
                """,
                (user_id, period_start),
            )
            category_rows = cur.fetchall()

            cur.execute(
                """
                SELECT COALESCE(SUM(total_amount),0) AS total_expense,
                       COUNT(*) AS total_receipts,
                       COALESCE(AVG(total_amount),0) AS avg_receipt_amount
                FROM receipts
                WHERE user_id=%s AND status='completed' AND receipt_date >= %s
                """,
                (user_id, period_start),
            )
            totals = cur.fetchone()

            cur.execute(
                """
                SELECT category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts
                WHERE user_id=%s AND status='completed' AND receipt_date >= %s
                GROUP BY category_id
                ORDER BY total DESC
                LIMIT 5
                """,
                (user_id, period_start),
            )
            top_categories = cur.fetchall()

        category_by_month = {}
        for row in category_rows:
            month_key = row["month"]
            if month_key not in category_by_month:
                category_by_month[month_key] = []
            category_by_month[month_key].append(
                {
                    "category_id": row["category_id"],
                    "category_name": CATEGORIES.get(row["category_id"], "Diğer"),
                    "total": round(_safe_float(row["total"]), 2),
                }
            )

        data = []
        for row in monthly_rows:
            month_key = row["month"]
            month_categories = category_by_month.get(month_key, [])
            top_category = month_categories[0] if month_categories else None
            data.append(
                {
                    "month": month_key,
                    "total_expense": round(_safe_float(row["total_expense"]), 2),
                    "avg_expense": round(_safe_float(row["avg_expense"]), 2),
                    "receipt_count": int(row["receipt_count"] or 0),
                    "top_category": top_category,
                    "categories": month_categories,
                }
            )

        return api_response(
            200,
            {
                "period_start": period_start.isoformat(),
                "period_end": today.isoformat(),
                "months": months,
                "currency": "TRY",
                "summary": {
                    "total_expense": round(_safe_float(totals["total_expense"]), 2),
                    "total_receipts": int(totals["total_receipts"] or 0),
                    "avg_receipt_amount": round(_safe_float(totals["avg_receipt_amount"]), 2),
                    "top_categories": [
                        {
                            "category_id": row["category_id"],
                            "category_name": CATEGORIES.get(row["category_id"], "Diğer"),
                            "total": round(_safe_float(row["total"]), 2),
                        }
                        for row in top_categories
                    ],
                },
                "data": data,
            },
        )
    finally:
        release_db_connection(conn)


def handle_get_budgets(user_id):
    period = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, user_id, category_name, amount, updated_at FROM budgets WHERE user_id=%s", (user_id,))
            rows = cur.fetchall()

            cur.execute(
                """
                SELECT category_id, SUM(total_amount) AS spent
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY category_id
                """,
                (user_id, period),
            )
            spent_rows = cur.fetchall()
            spent_map = {CATEGORIES.get(r["category_id"], "Diğer"): _safe_float(r["spent"]) for r in spent_rows}

            normalized = []
            for row in rows:
                spent = spent_map.get(row.get("category_name"), 0.0)
                limit_value = _safe_float(row.get("amount"), 0.0)
                pct = round((spent / limit_value) * 100, 1) if limit_value > 0 else 0.0
                row["spent"] = spent
                row["percentage"] = pct
                normalized.append(row)

            return api_response(200, {"data": normalized})
    finally:
        release_db_connection(conn)


def handle_set_budget(user_id, body):
    body = body or {}
    category_name = body.get("category_name")
    amount = _safe_float(body.get("amount"), None)
    if not category_name or amount is None:
        return api_response(400, {"error": "category_name and amount are required"})

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO budgets (user_id, category_name, amount)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, category_name)
                DO UPDATE SET amount=EXCLUDED.amount, updated_at=NOW()
                """,
                (user_id, category_name, amount),
            )
            conn.commit()
            return api_response(200, {"message": "Budget updated"})
    finally:
        release_db_connection(conn)


def handle_delete_budget(user_id, budget_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM budgets WHERE id=%s AND user_id=%s",
                (budget_id, user_id),
            )
            if cur.rowcount == 0:
                return api_response(404, {"error": "Budget not found"})
            conn.commit()
            return api_response(200, {"message": "Budget deleted"})
    finally:
        release_db_connection(conn)


def handle_subscriptions(user_id, method, body, sub_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if method == "GET":
                cur.execute(
                    "SELECT id, user_id, name, amount, next_payment_date, created_at FROM subscriptions WHERE user_id=%s ORDER BY id DESC",
                    (user_id,),
                )
                return api_response(200, {"data": cur.fetchall()})

            if method == "POST":
                body = body or {}
                name = body.get("name")
                amount = _safe_float(body.get("amount"), None)
                next_payment_date = body.get("next_payment_date")
                if not name or amount is None:
                    return api_response(400, {"error": "name and amount are required"})
                cur.execute(
                    """
                    INSERT INTO subscriptions (user_id, name, amount, next_payment_date)
                    VALUES (%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (user_id, name, amount, next_payment_date),
                )
                created = cur.fetchone()
                conn.commit()
                return api_response(201, {"message": "Subscription added", "id": created["id"]})

            if method in {"PUT", "PATCH"} and sub_id:
                body = body or {}
                cur.execute(
                    "SELECT id FROM subscriptions WHERE id=%s AND user_id=%s",
                    (sub_id, user_id),
                )
                if not cur.fetchone():
                    return api_response(404, {"error": "Subscription not found"})

                name = str(body.get("name") or "").strip()
                amount = _safe_float(body.get("amount"), None)
                next_payment_date = body.get("next_payment_date")

                if not name or amount is None or amount <= 0:
                    return api_response(400, {"error": "name and valid amount are required"})

                cur.execute(
                    """
                    UPDATE subscriptions
                    SET name=%s, amount=%s, next_payment_date=%s
                    WHERE id=%s AND user_id=%s
                    RETURNING id, name, amount, next_payment_date, created_at
                    """,
                    (name, amount, next_payment_date, sub_id, user_id),
                )
                updated = cur.fetchone()
                conn.commit()
                return api_response(200, updated)

            if method == "DELETE" and sub_id:
                cur.execute("DELETE FROM subscriptions WHERE id=%s AND user_id=%s", (sub_id, user_id))
                conn.commit()
                return api_response(200, {"message": "Deleted"})

            return api_response(400, {"error": "Invalid request"})
    finally:
        release_db_connection(conn)


def _normalize_goal_status(value, default="active"):
    allowed = {"active", "completed", "archived"}
    candidate = str(value or default).strip().lower()
    return candidate if candidate in allowed else default


def _normalize_goal_type(value, default="savings"):
    allowed = {"savings", "expense_reduction", "income_growth"}
    candidate = str(value or default).strip().lower()
    return candidate if candidate in allowed else default


def handle_goals(user_id, method, body, goal_id=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if method == "GET":
                cur.execute(
                    """
                    SELECT id,
                           title,
                           target_amount,
                           current_amount,
                           target_date,
                           metric_type,
                           status,
                           notes,
                           created_at,
                           updated_at,
                           CASE
                               WHEN target_amount > 0
                               THEN ROUND((current_amount / target_amount) * 100, 1)
                               ELSE 0
                           END AS progress_pct,
                           GREATEST(target_amount - current_amount, 0) AS remaining_amount
                    FROM financial_goals
                    WHERE user_id = %s
                      AND status != 'archived'
                    ORDER BY
                      CASE WHEN status = 'completed' THEN 1 ELSE 0 END ASC,
                      target_date NULLS LAST,
                      created_at DESC
                    """,
                    (user_id,),
                )
                return api_response(200, {"data": cur.fetchall()})

            if method == "POST":
                body = body or {}
                title = str(body.get("title") or "").strip()
                target_amount = _safe_float(body.get("target_amount"), None)
                current_amount = _safe_float(body.get("current_amount"), 0.0)
                target_date = body.get("target_date")
                metric_type = _normalize_goal_type(body.get("metric_type"))
                status = _normalize_goal_status(body.get("status"), "active")
                notes = str(body.get("notes") or "").strip()[:280]

                if not title or target_amount is None or target_amount <= 0:
                    return api_response(400, {"error": "title and positive target_amount are required"})
                if current_amount < 0:
                    return api_response(400, {"error": "current_amount cannot be negative"})

                cur.execute(
                    """
                    INSERT INTO financial_goals
                        (user_id, title, target_amount, current_amount, target_date, metric_type, status, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id, title, target_amount, current_amount, target_date, metric_type, status, notes, created_at, updated_at
                    """,
                    (user_id, title, target_amount, current_amount, target_date, metric_type, status, notes),
                )
                created = cur.fetchone()
                conn.commit()
                return api_response(201, created)

            if method == "PUT" and goal_id:
                body = body or {}
                cur.execute("SELECT id FROM financial_goals WHERE id=%s AND user_id=%s", (goal_id, user_id))
                if not cur.fetchone():
                    return api_response(404, {"error": "Goal not found"})

                title = body.get("title")
                target_amount = body.get("target_amount")
                current_amount = body.get("current_amount")
                target_date = body.get("target_date")
                metric_type = body.get("metric_type")
                status = body.get("status")
                notes = body.get("notes")

                fields = []
                values = []

                if title is not None:
                    title = str(title).strip()
                    if not title:
                        return api_response(400, {"error": "title cannot be empty"})
                    fields.append("title=%s")
                    values.append(title)

                if target_amount is not None:
                    target_amount = _safe_float(target_amount, None)
                    if target_amount is None or target_amount <= 0:
                        return api_response(400, {"error": "target_amount must be positive"})
                    fields.append("target_amount=%s")
                    values.append(target_amount)

                if current_amount is not None:
                    current_amount = _safe_float(current_amount, None)
                    if current_amount is None or current_amount < 0:
                        return api_response(400, {"error": "current_amount cannot be negative"})
                    fields.append("current_amount=%s")
                    values.append(current_amount)

                if target_date is not None:
                    fields.append("target_date=%s")
                    values.append(target_date or None)

                if metric_type is not None:
                    fields.append("metric_type=%s")
                    values.append(_normalize_goal_type(metric_type))

                if status is not None:
                    fields.append("status=%s")
                    values.append(_normalize_goal_status(status))

                if notes is not None:
                    fields.append("notes=%s")
                    values.append(str(notes).strip()[:280])

                if not fields:
                    return api_response(400, {"error": "No updatable fields provided"})

                fields.append("updated_at=NOW()")
                values.extend([goal_id, user_id])
                cur.execute(
                    f"""
                    UPDATE financial_goals
                    SET {', '.join(fields)}
                    WHERE id=%s AND user_id=%s
                    RETURNING id, title, target_amount, current_amount, target_date, metric_type, status, notes, created_at, updated_at
                    """,
                    tuple(values),
                )
                updated = cur.fetchone()
                conn.commit()
                return api_response(200, updated)

            if method == "DELETE" and goal_id:
                cur.execute(
                    "UPDATE financial_goals SET status='archived', updated_at=NOW() WHERE id=%s AND user_id=%s",
                    (goal_id, user_id),
                )
                conn.commit()
                return api_response(200, {"message": "Goal archived"})

            return api_response(400, {"error": "Invalid request"})
    finally:
        release_db_connection(conn)


def handle_insights_overview(user_id, params):
    params = params or {}
    period, period_start, period_end = _period_bounds(params.get("month"))
    days_in_month = (period_end - period_start).days + 1
    is_current_period = period == datetime.now().strftime("%Y-%m")
    elapsed_days = datetime.now().day if is_current_period else days_in_month
    elapsed_days = max(1, min(elapsed_days, days_in_month))

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS tx_count,
                       COALESCE(SUM(total_amount), 0) AS total_spent
                FROM receipts
                WHERE user_id=%s
                  AND status != 'deleted'
                  AND receipt_date BETWEEN %s AND %s
                """,
                (user_id, period_start, period_end),
            )
            spending_row = cur.fetchone() or {"tx_count": 0, "total_spent": 0}

            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total_income
                FROM incomes
                WHERE user_id=%s
                  AND income_date BETWEEN %s AND %s
                """,
                (user_id, period_start, period_end),
            )
            income_row = cur.fetchone() or {"total_income": 0}

            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total_subscriptions
                FROM subscriptions
                WHERE user_id=%s
                """,
                (user_id,),
            )
            sub_row = cur.fetchone() or {"total_subscriptions": 0}

            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total_fixed
                FROM fixed_expense_items
                WHERE user_id=%s AND is_active=TRUE
                """,
                (user_id,),
            )
            fixed_row = cur.fetchone() or {"total_fixed": 0}

            cur.execute("SELECT category_name, amount FROM budgets WHERE user_id=%s", (user_id,))
            budgets = cur.fetchall() or []

            cur.execute(
                """
                SELECT category_id, COALESCE(SUM(total_amount),0) AS spent
                FROM receipts
                WHERE user_id=%s
                  AND status != 'deleted'
                  AND receipt_date BETWEEN %s AND %s
                GROUP BY category_id
                """,
                (user_id, period_start, period_end),
            )
            spent_rows = cur.fetchall() or []
            spent_by_category = {
                CATEGORIES.get(r.get("category_id"), "Diger").lower(): _safe_float(r.get("spent"))
                for r in spent_rows
            }

            budgets_count = len(budgets)
            met_count = 0
            for b in budgets:
                category = str(b.get("category_name") or "").strip().lower()
                limit_amount = _safe_float(b.get("amount"), 0.0)
                spent_amount = spent_by_category.get(category, 0.0)
                if limit_amount > 0 and spent_amount <= limit_amount:
                    met_count += 1

            cur.execute(
                """
                SELECT category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts
                WHERE user_id=%s
                  AND status != 'deleted'
                  AND receipt_date BETWEEN %s AND %s
                GROUP BY category_id
                ORDER BY total DESC
                LIMIT 4
                """,
                (user_id, period_start, period_end),
            )
            top_rows = cur.fetchall() or []

            cur.execute(
                """
                SELECT COUNT(*) FILTER (WHERE status='active') AS active_count,
                       COUNT(*) FILTER (WHERE status='completed') AS completed_count,
                       COALESCE(SUM(target_amount) FILTER (WHERE status='active'), 0) AS active_target_total,
                       COALESCE(SUM(current_amount) FILTER (WHERE status='active'), 0) AS active_current_total
                FROM financial_goals
                WHERE user_id=%s
                """,
                (user_id,),
            )
            goals_row = cur.fetchone() or {}

            cur.execute(
                """
                SELECT id, title, target_date, target_amount, current_amount, status
                FROM financial_goals
                WHERE user_id=%s
                  AND status='active'
                  AND target_date IS NOT NULL
                  AND target_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '14 days')
                ORDER BY target_date ASC
                LIMIT 5
                """,
                (user_id,),
            )
            goals_due_soon = cur.fetchall() or []

            total_spent = round(_safe_float(spending_row.get("total_spent")), 2)
            total_income = round(_safe_float(income_row.get("total_income")), 2)
            tx_count = int(spending_row.get("tx_count") or 0)
            total_subscriptions = round(_safe_float(sub_row.get("total_subscriptions")), 2)
            total_fixed = round(_safe_float(fixed_row.get("total_fixed")), 2)
            net_balance = round(total_income - total_spent, 2)
            savings_rate = round(((total_income - total_spent) / total_income) * 100, 1) if total_income > 0 else 0.0
            subscription_share = round((total_subscriptions / total_spent) * 100, 1) if total_spent > 0 else 0.0
            fixed_share = round((total_fixed / total_spent) * 100, 1) if total_spent > 0 else 0.0
            budget_adherence = round((met_count / budgets_count) * 100, 1) if budgets_count > 0 else 0.0
            daily_burn = round(total_spent / elapsed_days, 2)
            projected_month_end = round(daily_burn * days_in_month, 2)

            recommendations = []
            if total_income > 0 and savings_rate < 10:
                recommendations.append("Tasarruf oranını %10 üzerine çıkarmak için yüksek harcama kategorinde mikro limit uygula.")
            if budgets_count > 0 and budget_adherence < 70:
                recommendations.append("Bütçe hedeflerinin çoğu aşılmış görünüyor; aylık limitleri güncelle ve kritik kategoriye uyarı koy.")
            if subscription_share > 20:
                recommendations.append("Abonelik giderlerinin toplam harcamadaki payı yüksek; kullanmadığın abonelikleri iptal et.")
            if fixed_share > 60:
                recommendations.append("Sabit gider oranı çok yüksek; pazarlık yapılabilir kalemleri yeniden fiyatlandır.")
            if int(goals_row.get("active_count") or 0) == 0:
                recommendations.append("En az bir aktif finansal hedef ekleyerek AI analizini kişiselleştir.")

            top_categories = [
                {
                    "name": CATEGORIES.get(r.get("category_id"), "Diger"),
                    "total": round(_safe_float(r.get("total")), 2),
                }
                for r in top_rows
            ]

            goal_progress_pct = 0.0
            active_target_total = _safe_float(goals_row.get("active_target_total"), 0.0)
            active_current_total = _safe_float(goals_row.get("active_current_total"), 0.0)
            if active_target_total > 0:
                goal_progress_pct = round((active_current_total / active_target_total) * 100, 1)

            return api_response(
                200,
                {
                    "period": period,
                    "financial_health": {
                        "total_spent": total_spent,
                        "total_income": total_income,
                        "net_balance": net_balance,
                        "savings_rate": savings_rate,
                        "daily_burn": daily_burn,
                        "projected_month_end_spend": projected_month_end,
                        "transactions_count": tx_count,
                    },
                    "structure": {
                        "subscription_total": total_subscriptions,
                        "subscription_share": subscription_share,
                        "fixed_expense_total": total_fixed,
                        "fixed_expense_share": fixed_share,
                        "budget_adherence": budget_adherence,
                        "budgets_met": met_count,
                        "budgets_total": budgets_count,
                        "top_categories": top_categories,
                    },
                    "goals": {
                        "active_count": int(goals_row.get("active_count") or 0),
                        "completed_count": int(goals_row.get("completed_count") or 0),
                        "active_target_total": round(active_target_total, 2),
                        "active_current_total": round(active_current_total, 2),
                        "active_progress_pct": goal_progress_pct,
                        "due_soon": goals_due_soon,
                    },
                    "recommendations": recommendations[:5],
                    "meta": {
                        "generated_at": datetime.utcnow().isoformat() + "Z",
                        "days_in_month": days_in_month,
                        "elapsed_days": elapsed_days,
                    },
                },
            )
    finally:
        release_db_connection(conn)


def _normalize_action_status(value, default="pending"):
    allowed = {"pending", "done", "dismissed"}
    candidate = str(value or default).strip().lower()
    return candidate if candidate in allowed else default


def _normalize_action_priority(value, default="MEDIUM"):
    allowed = {"HIGH", "MEDIUM", "LOW"}
    candidate = str(value or default).strip().upper()
    return candidate if candidate in allowed else default


def handle_ai_actions(user_id, method, body, action_id=None, params=None):
    body = body or {}
    params = params or {}
    period = _parse_period((body or {}).get("month") or (params or {}).get("month"))

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if method == "GET":
                cur.execute(
                    """
                    SELECT id, related_period, title, source_insight, priority, status, due_date, done_at, created_at, updated_at
                    FROM ai_action_items
                    WHERE user_id=%s AND related_period=%s
                    ORDER BY
                      CASE status WHEN 'pending' THEN 0 WHEN 'done' THEN 1 ELSE 2 END,
                      priority DESC,
                      due_date NULLS LAST,
                      created_at DESC
                    """,
                    (user_id, period),
                )
                rows = cur.fetchall() or []
                done_count = len([r for r in rows if str(r.get("status")) == "done"])
                return api_response(
                    200,
                    {
                        "month": period,
                        "data": rows,
                        "stats": {
                            "total": len(rows),
                            "done": done_count,
                            "pending": len(rows) - done_count,
                        },
                    },
                )

            if method == "POST":
                actions = body.get("actions")
                if not isinstance(actions, list):
                    title = str(body.get("title") or "").strip()
                    if not title:
                        return api_response(400, {"error": "actions list or title is required"})
                    actions = [
                        {
                            "title": title,
                            "priority": body.get("priority", "MEDIUM"),
                            "source_insight": body.get("source_insight"),
                            "due_in_days": body.get("due_in_days"),
                        }
                    ]

                inserted = 0
                for action in actions[:50]:
                    title = str(action.get("title") or "").strip()
                    if not title:
                        continue
                    source_insight = str(action.get("source_insight") or "").strip()[:64]
                    priority = _normalize_action_priority(action.get("priority"), "MEDIUM")
                    due_in_days = int(_safe_float(action.get("due_in_days"), 0))
                    due_date = date.today() + timedelta(days=max(0, min(due_in_days, 90))) if due_in_days > 0 else None

                    cur.execute(
                        """
                        INSERT INTO ai_action_items (user_id, related_period, title, source_insight, priority, status, due_date)
                        VALUES (%s,%s,%s,%s,%s,'pending',%s)
                        ON CONFLICT (user_id, related_period, title)
                        DO UPDATE SET
                          priority = EXCLUDED.priority,
                          source_insight = COALESCE(NULLIF(EXCLUDED.source_insight, ''), ai_action_items.source_insight),
                          due_date = COALESCE(EXCLUDED.due_date, ai_action_items.due_date),
                          updated_at = NOW()
                        """,
                        (user_id, period, title[:180], source_insight, priority, due_date),
                    )
                    inserted += 1

                conn.commit()
                return api_response(200, {"message": "Actions synced", "processed": inserted, "month": period})

            if method in {"PUT", "PATCH"} and action_id:
                status = _normalize_action_status(body.get("status"), None)
                if not status:
                    return api_response(400, {"error": "status is required"})

                done_at = datetime.utcnow() if status == "done" else None
                cur.execute(
                    """
                    UPDATE ai_action_items
                    SET status=%s,
                        done_at=%s,
                        updated_at=NOW()
                    WHERE id=%s AND user_id=%s
                    RETURNING id, related_period, title, source_insight, priority, status, due_date, done_at, updated_at
                    """,
                    (status, done_at, action_id, user_id),
                )
                updated = cur.fetchone()
                if not updated:
                    return api_response(404, {"error": "Action not found"})
                conn.commit()
                return api_response(200, updated)

            if method == "DELETE" and action_id:
                cur.execute("DELETE FROM ai_action_items WHERE id=%s AND user_id=%s", (action_id, user_id))
                conn.commit()
                return api_response(200, {"message": "Deleted"})

            return api_response(400, {"error": "Invalid request"})
    finally:
        release_db_connection(conn)


def handle_insights_what_if(user_id, params):
    params = params or {}
    period, period_start, period_end = _period_bounds(params.get("month"))
    raw_category = str(params.get("category") or "").strip().lower()
    cut_percent = max(0.0, min(_safe_float(params.get("cut_percent"), 10.0), 90.0))

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts
                WHERE user_id=%s
                  AND status != 'deleted'
                  AND receipt_date BETWEEN %s AND %s
                GROUP BY category_id
                ORDER BY total DESC
                """,
                (user_id, period_start, period_end),
            )
            category_rows = cur.fetchall() or []

            cur.execute(
                """
                SELECT COALESCE(SUM(total_amount), 0) AS total_spent
                FROM receipts
                WHERE user_id=%s
                  AND status != 'deleted'
                  AND receipt_date BETWEEN %s AND %s
                """,
                (user_id, period_start, period_end),
            )
            total_spent = _safe_float((cur.fetchone() or {}).get("total_spent"), 0.0)

            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total_income
                FROM incomes
                WHERE user_id=%s
                  AND income_date BETWEEN %s AND %s
                """,
                (user_id, period_start, period_end),
            )
            total_income = _safe_float((cur.fetchone() or {}).get("total_income"), 0.0)

            if not category_rows:
                return api_response(
                    200,
                    {
                        "month": period,
                        "scenario": None,
                        "summary": "No spending data for selected month",
                    },
                )

            selected = None
            if raw_category:
                for row in category_rows:
                    name = CATEGORIES.get(row.get("category_id"), "Diger")
                    if _normalize_text(name) == _normalize_text(raw_category):
                        selected = row
                        break
            if selected is None:
                selected = category_rows[0]

            category_name = CATEGORIES.get(selected.get("category_id"), "Diger")
            category_total = _safe_float(selected.get("total"), 0.0)
            estimated_saving = round(category_total * (cut_percent / 100.0), 2)
            projected_spent = round(max(total_spent - estimated_saving, 0.0), 2)
            current_savings_rate = round(((total_income - total_spent) / total_income) * 100, 1) if total_income > 0 else 0.0
            projected_savings_rate = round(((total_income - projected_spent) / total_income) * 100, 1) if total_income > 0 else current_savings_rate

            return api_response(
                200,
                {
                    "month": period,
                    "scenario": {
                        "category": category_name,
                        "cut_percent": round(cut_percent, 1),
                        "category_total": round(category_total, 2),
                        "estimated_saving": estimated_saving,
                        "current_total_spent": round(total_spent, 2),
                        "projected_total_spent": projected_spent,
                        "current_savings_rate": current_savings_rate,
                        "projected_savings_rate": projected_savings_rate,
                    },
                    "available_categories": [
                        {
                            "name": CATEGORIES.get(r.get("category_id"), "Diger"),
                            "total": round(_safe_float(r.get("total")), 2),
                        }
                        for r in category_rows[:8]
                    ],
                },
            )
    finally:
        release_db_connection(conn)


def _fixed_expense_status(month_payment, due_date, period):
    if month_payment:
        status = str(month_payment.get("status") or "").strip().lower()
        if status in {"paid", "pending"}:
            return status
    if due_date < date.today() and period == datetime.now().strftime("%Y-%m"):
        return "overdue"
    return "pending"


def handle_fixed_expenses_get(user_id, params):
    params = params or {}
    period, period_start, period_end = _period_bounds(params.get("month"))

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT g.id AS group_id,
                       g.title,
                       g.category_type,
                       g.created_at AS group_created_at,
                       i.id AS item_id,
                       i.name AS item_name,
                       i.amount AS item_amount,
                       i.due_day,
                       i.created_at AS item_created_at
                FROM fixed_expense_groups g
                LEFT JOIN fixed_expense_items i
                       ON i.group_id = g.id
                      AND i.is_active = TRUE
                WHERE g.user_id = %s
                  AND g.is_active = TRUE
                ORDER BY g.created_at DESC, i.due_day ASC, i.created_at ASC
                """,
                (user_id,),
            )
            rows = cur.fetchall()

            if not rows:
                return api_response(
                    200,
                    {
                        "month": period,
                        "stats": {"total": 0, "paid": 0, "remaining": 0, "count": 0, "pending_count": 0},
                        "data": [],
                    },
                )

            item_ids = [str(r["item_id"]) for r in rows if r.get("item_id")]

            month_payments = {}
            if item_ids:
                cur.execute(
                    """
                    SELECT id, item_id, payment_date, amount, status, note, source, created_at, updated_at
                    FROM fixed_expense_payments
                    WHERE user_id=%s
                      AND item_id = ANY(%s::uuid[])
                      AND payment_date >= %s
                      AND payment_date <= %s
                    ORDER BY payment_date DESC, created_at DESC
                    """,
                    (user_id, item_ids, period_start, period_end),
                )
                for pay in cur.fetchall():
                    key = str(pay["item_id"])
                    if key not in month_payments:
                        month_payments[key] = pay

            history_map = {}
            if item_ids:
                cur.execute(
                    """
                    SELECT id, item_id, payment_date, amount, status
                    FROM (
                        SELECT id, item_id, payment_date, amount, status, created_at,
                               ROW_NUMBER() OVER (
                                   PARTITION BY item_id
                                   ORDER BY payment_date DESC, created_at DESC
                               ) AS rn
                        FROM fixed_expense_payments
                        WHERE user_id=%s
                          AND item_id = ANY(%s::uuid[])
                    ) ranked
                    WHERE rn <= 6
                    ORDER BY item_id, payment_date DESC
                    """,
                    (user_id, item_ids),
                )
                for row in cur.fetchall():
                    key = str(row["item_id"])
                    history_map.setdefault(key, []).append(
                        {
                            "id": row["id"],
                            "date": row["payment_date"],
                            "amount": _safe_float(row["amount"]),
                            "status": row["status"],
                        }
                    )

            group_map = {}
            for row in rows:
                gid = str(row["group_id"])
                if gid not in group_map:
                    group_map[gid] = {
                        "id": row["group_id"],
                        "title": row["title"],
                        "category_type": row["category_type"] or "Diger",
                        "items": [],
                    }

                if not row.get("item_id"):
                    continue

                item_id = str(row["item_id"])
                due_day = int(row.get("due_day") or 1)
                due_date = _resolve_due_date_for_period(period, due_day)
                month_payment = month_payments.get(item_id)
                status = _fixed_expense_status(month_payment, due_date, period)
                amount = _safe_float(row.get("item_amount"), 0.0)

                group_map[gid]["items"].append(
                    {
                        "id": row["item_id"],
                        "name": row["item_name"] or "Gider",
                        "amount": amount,
                        "day": due_day,
                        "due_date": due_date.isoformat(),
                        "status": status,
                        "month_payment": {
                            "id": (month_payment or {}).get("id"),
                            "payment_date": (month_payment or {}).get("payment_date"),
                            "amount": _safe_float((month_payment or {}).get("amount"), 0.0),
                            "status": (month_payment or {}).get("status"),
                        } if month_payment else None,
                        "history": history_map.get(item_id, []),
                    }
                )

            groups = list(group_map.values())

            total = 0.0
            paid = 0.0
            count = 0
            pending_count = 0
            for group in groups:
                group_total = 0.0
                for item in group["items"]:
                    count += 1
                    group_total += _safe_float(item["amount"], 0.0)
                    total += _safe_float(item["amount"], 0.0)
                    if item["status"] == "paid":
                        paid += _safe_float(item["amount"], 0.0)
                    else:
                        pending_count += 1
                group["total_amount"] = round(group_total, 2)

            return api_response(
                200,
                {
                    "month": period,
                    "stats": {
                        "total": round(total, 2),
                        "paid": round(paid, 2),
                        "remaining": round(max(total - paid, 0), 2),
                        "count": count,
                        "pending_count": pending_count,
                    },
                    "data": groups,
                },
            )
    finally:
        release_db_connection(conn)


def handle_fixed_expense_group_create(user_id, body):
    body = body or {}
    title = str(body.get("title") or "").strip()
    category_type = str(body.get("category_type") or "Diger").strip()[:80]

    if not title:
        return api_response(400, {"error": "title is required"})

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO fixed_expense_groups (user_id, title, category_type)
                VALUES (%s,%s,%s)
                RETURNING id, title, category_type, created_at, updated_at
                """,
                (user_id, title[:150], category_type),
            )
            created = cur.fetchone()
            conn.commit()
            return api_response(201, created)
    finally:
        release_db_connection(conn)


def handle_fixed_expense_group_update(user_id, group_id, body):
    body = body or {}
    updates = []
    values = []

    if body.get("title") is not None:
        title = str(body.get("title") or "").strip()
        if not title:
            return api_response(400, {"error": "title cannot be empty"})
        updates.append("title=%s")
        values.append(title[:150])

    if body.get("category_type") is not None:
        updates.append("category_type=%s")
        values.append(str(body.get("category_type") or "Diger").strip()[:80])

    if body.get("is_active") is not None:
        is_active = _coerce_bool(body.get("is_active"), None)
        if is_active is None:
            return api_response(400, {"error": "is_active must be boolean"})
        updates.append("is_active=%s")
        values.append(is_active)

    if not updates:
        return api_response(400, {"error": "No valid fields to update"})

    updates.append("updated_at=NOW()")
    values.extend([group_id, user_id])

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                UPDATE fixed_expense_groups
                SET {", ".join(updates)}
                WHERE id=%s AND user_id=%s
                RETURNING id, title, category_type, is_active, created_at, updated_at
                """,
                values,
            )
            updated = cur.fetchone()
            if not updated:
                return api_response(404, {"error": "Group not found"})
            conn.commit()
            return api_response(200, updated)
    finally:
        release_db_connection(conn)


def handle_fixed_expense_group_delete(user_id, group_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE fixed_expense_groups
                SET is_active=FALSE, updated_at=NOW()
                WHERE id=%s AND user_id=%s
                RETURNING id
                """,
                (group_id, user_id),
            )
            group = cur.fetchone()
            if not group:
                return api_response(404, {"error": "Group not found"})

            cur.execute(
                """
                UPDATE fixed_expense_items
                SET is_active=FALSE, updated_at=NOW()
                WHERE group_id=%s AND user_id=%s
                """,
                (group_id, user_id),
            )
            conn.commit()
            return api_response(200, {"message": "Deleted"})
    finally:
        release_db_connection(conn)


def handle_fixed_expense_item_create(user_id, body):
    body = body or {}
    group_id = body.get("group_id")
    name = str(body.get("name") or "").strip()
    amount = _safe_float(body.get("amount"), None)
    due_day = body.get("day")

    if not group_id or not name or amount is None:
        return api_response(400, {"error": "group_id, name and amount are required"})
    if amount <= 0:
        return api_response(400, {"error": "amount must be greater than 0"})

    try:
        due_day = int(due_day)
        if due_day < 1 or due_day > 31:
            raise ValueError()
    except Exception:
        return api_response(400, {"error": "day must be between 1 and 31"})

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id
                FROM fixed_expense_groups
                WHERE id=%s AND user_id=%s AND is_active=TRUE
                """,
                (group_id, user_id),
            )
            if not cur.fetchone():
                return api_response(404, {"error": "Group not found"})

            cur.execute(
                """
                INSERT INTO fixed_expense_items (group_id, user_id, name, amount, due_day)
                VALUES (%s,%s,%s,%s,%s)
                RETURNING id, group_id, name, amount, due_day, created_at, updated_at
                """,
                (group_id, user_id, name[:150], amount, due_day),
            )
            created = cur.fetchone()
            conn.commit()
            return api_response(201, created)
    finally:
        release_db_connection(conn)


def handle_fixed_expense_item_update(user_id, item_id, body):
    body = body or {}
    updates = []
    values = []

    if body.get("name") is not None:
        name = str(body.get("name") or "").strip()
        if not name:
            return api_response(400, {"error": "name cannot be empty"})
        updates.append("name=%s")
        values.append(name[:150])

    if body.get("amount") is not None:
        amount = _safe_float(body.get("amount"), None)
        if amount is None or amount <= 0:
            return api_response(400, {"error": "amount must be greater than 0"})
        updates.append("amount=%s")
        values.append(amount)

    if body.get("day") is not None:
        try:
            due_day = int(body.get("day"))
            if due_day < 1 or due_day > 31:
                raise ValueError()
            updates.append("due_day=%s")
            values.append(due_day)
        except Exception:
            return api_response(400, {"error": "day must be between 1 and 31"})

    if body.get("is_active") is not None:
        is_active = _coerce_bool(body.get("is_active"), None)
        if is_active is None:
            return api_response(400, {"error": "is_active must be boolean"})
        updates.append("is_active=%s")
        values.append(is_active)

    if not updates:
        return api_response(400, {"error": "No valid fields to update"})

    updates.append("updated_at=NOW()")
    values.extend([item_id, user_id])

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                UPDATE fixed_expense_items
                SET {", ".join(updates)}
                WHERE id=%s AND user_id=%s
                RETURNING id, group_id, name, amount, due_day, is_active, created_at, updated_at
                """,
                values,
            )
            updated = cur.fetchone()
            if not updated:
                return api_response(404, {"error": "Item not found"})
            conn.commit()
            return api_response(200, updated)
    finally:
        release_db_connection(conn)


def handle_fixed_expense_item_delete(user_id, item_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE fixed_expense_items
                SET is_active=FALSE, updated_at=NOW()
                WHERE id=%s AND user_id=%s
                RETURNING id
                """,
                (item_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                return api_response(404, {"error": "Item not found"})
            conn.commit()
            return api_response(200, {"message": "Deleted"})
    finally:
        release_db_connection(conn)


def handle_fixed_expense_payment_upsert(user_id, item_id, body):
    body = body or {}
    status = str(body.get("status") or "paid").strip().lower()
    if status not in {"paid", "pending"}:
        return api_response(400, {"error": "status must be paid or pending"})

    month = body.get("month")
    payment_date_raw = body.get("payment_date")
    note = re.sub(r"\s+", " ", str(body.get("note") or "")).strip()[:280]
    source = str(body.get("source") or "manual").strip()[:40]

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT i.id, i.amount, i.due_day
                FROM fixed_expense_items i
                JOIN fixed_expense_groups g ON g.id=i.group_id
                WHERE i.id=%s
                  AND i.user_id=%s
                  AND i.is_active=TRUE
                  AND g.is_active=TRUE
                """,
                (item_id, user_id),
            )
            item = cur.fetchone()
            if not item:
                return api_response(404, {"error": "Item not found"})

            if payment_date_raw:
                try:
                    payment_date = datetime.strptime(str(payment_date_raw), "%Y-%m-%d").date()
                except Exception:
                    return api_response(400, {"error": "payment_date must be YYYY-MM-DD"})
            elif month:
                payment_date = _resolve_due_date_for_period(month, item.get("due_day") or 1)
            else:
                payment_date = date.today()

            amount = _safe_float(body.get("amount"), _safe_float(item.get("amount"), 0.0))
            if amount <= 0:
                return api_response(400, {"error": "amount must be greater than 0"})

            cur.execute(
                """
                INSERT INTO fixed_expense_payments (
                    item_id, user_id, payment_date, amount, status, note, source
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (item_id, payment_date)
                DO UPDATE SET
                    amount=EXCLUDED.amount,
                    status=EXCLUDED.status,
                    note=EXCLUDED.note,
                    source=EXCLUDED.source,
                    updated_at=NOW()
                RETURNING id, item_id, payment_date, amount, status, note, source, created_at, updated_at
                """,
                (item_id, user_id, payment_date, amount, status, note, source),
            )
            payment = cur.fetchone()
            conn.commit()
            return api_response(200, payment)
    finally:
        release_db_connection(conn)


def _compute_data_signature(total_amount, receipt_count, last_upd, persona="friendly"):
    raw = f"{_safe_float(total_amount)}-{int(receipt_count)}-{last_upd}-{persona}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def handle_ai_analyze(user_id, body):
    body = body or {}
    period = _parse_period(body.get("period"))
    skip_llm = bool(body.get("skipLLM", False))
    use_cache = bool(body.get("useCache", True))
    force_recompute = bool(body.get("forceRecompute", False))
    persona = str(body.get("persona") or "friendly").strip()

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count, COALESCE(SUM(total_amount),0) AS total, MAX(updated_at) AS last_upd
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                """,
                (user_id, period),
            )
            sig_row = cur.fetchone()
            
            # 2. Check if we have enough data - CRITICAL FIX
            if not sig_row or sig_row["count"] < 1:
                empty_analysis = {
                    "coach": {
                        "headline": "Analiz için yeterli veri yok.",
                        "summary": "Bu ay için henüz analiz edilecek harcama verisi bulunamadı.",
                        "focus_areas": ["Fiş ekleme", "Kategori düzeni", "Bütçe takibi"],
                    },
                    "insights": [
                        {
                            "id": "ins_low_data_1",
                            "type": "data_readiness",
                            "priority": "MEDIUM",
                            "title": "Yapay zeka analizi için veri biriktirin",
                            "summary": "Daha doğru tahmin ve öneriler için bu ay en az birkaç harcama kaydı ekleyin.",
                            "confidence": 95,
                            "actions": ["Manuel gider ekleyin", "Fiş yükleyin", "Sesli asistanla kayıt oluşturun"],
                        }
                    ],
                    "anomalies": [],
                    "forecast": {
                        "next_month_estimate": 0,
                        "trend": "stable",
                        "confidence_score": 0,
                    },
                    "patterns": {},
                    "next_actions": [
                        {"title": "Bu ay en az 3 harcamayı sisteme girin", "priority": "MEDIUM", "due_in_days": 7}
                    ],
                    "meta": {
                        "generated_at": datetime.utcnow().isoformat() + "Z",
                        "analysis_version": "v5",
                        "period": period,
                        "model_version": BEDROCK_MODEL_ID,
                        "cache_hit": False,
                        "insufficient_data": True,
                    },
                }
                try:
                    empty_meta = {
                        "generated_at": datetime.utcnow().isoformat(),
                        "data_sig": _compute_data_signature(sig_row["total"], sig_row["count"], sig_row["last_upd"] or datetime.min, persona),
                        "model": BEDROCK_MODEL_ID,
                        "cache_hit": False,
                        "ttl_seconds": AI_CACHE_TTL_SECONDS,
                    }
                    cur.execute("DELETE FROM ai_insights WHERE user_id=%s AND related_period=%s", (user_id, period))
                    cur.execute(
                        "INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) VALUES (%s,%s,%s,%s)",
                        (user_id, "__meta__", json.dumps(empty_meta, default=_json_default), period),
                    )
                    cur.execute(
                        "INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) VALUES (%s,%s,%s,%s)",
                        (user_id, "__result__", json.dumps(empty_analysis, default=_json_default), period),
                    )
                    conn.commit()
                except Exception as e:
                    logger.error(f"Failed to save empty state: {e}")

                return api_response(200, empty_analysis)

            current_data_sig = _compute_data_signature(sig_row["total"], sig_row["count"], sig_row["last_upd"] or datetime.min, persona)

            cached_meta = None
            cached_result = None
            if use_cache and not force_recompute:
                cur.execute(
                    """
                    SELECT insight_type, insight_text
                    FROM ai_insights
                    WHERE user_id=%s AND related_period=%s AND insight_type IN ('__meta__','__result__')
                    ORDER BY created_at DESC
                    """,
                    (user_id, period),
                )
                cached_rows = cur.fetchall()
                for row in cached_rows:
                    if row["insight_type"] == "__meta__" and cached_meta is None:
                        cached_meta = row["insight_text"]
                    if row["insight_type"] == "__result__" and cached_result is None:
                        cached_result = row["insight_text"]

                if isinstance(cached_meta, str):
                    try:
                        cached_meta = json.loads(cached_meta)
                    except Exception:
                        cached_meta = None
                if isinstance(cached_result, str):
                    try:
                        cached_result = json.loads(cached_result)
                    except Exception:
                        cached_result = None

                if isinstance(cached_meta, dict) and isinstance(cached_result, dict):
                    generated_at = cached_meta.get("generated_at")
                    cached_sig = cached_meta.get("data_sig")
                    if generated_at and cached_sig == current_data_sig:
                        try:
                            age_seconds = (datetime.utcnow() - datetime.fromisoformat(generated_at)).total_seconds()
                            if age_seconds <= AI_CACHE_TTL_SECONDS:
                                cached_result["is_stale"] = False
                                if not isinstance(cached_result.get("meta"), dict):
                                    cached_result["meta"] = {}
                                cached_result["meta"]["cache_hit"] = True
                                cached_result["meta"]["cache_age_seconds"] = int(age_seconds)
                                return api_response(200, cached_result)
                        except Exception:
                            pass

            period_start = f"{period}-01"
            cur.execute(
                """
                SELECT merchant_name AS merchant,
                       total_amount AS amount,
                       TO_CHAR(receipt_date, 'YYYY-MM-DD') AS date,
                       category_id
                FROM receipts
                WHERE user_id=%s
                  AND status != 'deleted'
                  AND receipt_date >= DATE(%s) - INTERVAL '6 months'
                ORDER BY receipt_date ASC
                """,
                (user_id, period_start),
            )
            txs = cur.fetchall()
            for tx in txs:
                tx["category"] = CATEGORIES.get(tx.get("category_id"), "Diğer")
                tx["amount"] = _safe_float(tx.get("amount"))

            cur.execute(
                """
                SELECT TO_CHAR(DATE_TRUNC('month', receipt_date), 'YYYY-MM') AS month,
                       category_id,
                       SUM(total_amount) AS total
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND receipt_date IS NOT NULL
                GROUP BY 1,2
                ORDER BY 1
                """,
                (user_id,),
            )
            monthly_rows = cur.fetchall()
            month_map = {}
            for row in monthly_rows:
                month = row["month"]
                if not month: continue # Skip if None
                
                if month not in month_map:
                    month_map[month] = {"month": month, "total": 0.0, "categories": {}}
                cat_name = CATEGORIES.get(row.get("category_id"), "Diğer")
                cat_total = _safe_float(row.get("total"))
                month_map[month]["categories"][cat_name] = round(cat_total, 2)
                month_map[month]["total"] += cat_total

            monthly = []
            # Robust Sort: Filter out any lingering None keys just in case
            valid_months = [m for m in month_map.keys() if m]
            for month in sorted(valid_months):
                month_map[month]["total"] = round(month_map[month]["total"], 2)
                monthly.append(month_map[month])

            cur.execute("SELECT category_name, amount FROM budgets WHERE user_id=%s", (user_id,))
            budget_rows = cur.fetchall()

            cur.execute(
                """
                SELECT category_id, SUM(total_amount) AS spent
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY category_id
                """,
                (user_id, period),
            )
            spent_rows = cur.fetchall()
            spent_map = {CATEGORIES.get(r["category_id"], "Diğer"): _safe_float(r["spent"]) for r in spent_rows}

            budgets = []
            for budget in budget_rows:
                category = budget.get("category_name")
                limit_value = _safe_float(budget.get("amount"))
                spent_value = spent_map.get(category, 0.0)
                pct = round((spent_value / limit_value) * 100, 1) if limit_value > 0 else 0.0
                budgets.append(
                    {
                        "category": category,
                        "limit": limit_value,
                        "spent": spent_value,
                        "pct": pct,
                        "budget": limit_value,
                    }
                )

            cur.execute("SELECT name, amount FROM subscriptions WHERE user_id=%s", (user_id,))
            subscriptions = cur.fetchall()

            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM incomes
                WHERE user_id=%s AND TO_CHAR(income_date, 'YYYY-MM')=%s
                """,
                (user_id, period),
            )
            income_total = _safe_float((cur.fetchone() or {}).get("total"), 0.0)

            cur.execute(
                """
                SELECT id, title, target_amount, current_amount, target_date, metric_type, status
                FROM financial_goals
                WHERE user_id=%s AND status='active'
                ORDER BY target_date NULLS LAST, created_at DESC
                LIMIT 30
                """,
                (user_id,),
            )
            goals = cur.fetchall()

            spent_total = _safe_float(sig_row.get("total"), 0.0)
            savings_rate = ((income_total - spent_total) / income_total * 100) if income_total > 0 else 0.0

            payload = {
                "transactions": txs,
                "monthlyTotals": monthly,
                "budgets": budgets,
                "subscriptions": subscriptions,
                "goals": goals,
                "financialHealth": {
                    "period_income": round(income_total, 2),
                    "period_spent": round(spent_total, 2),
                    "period_net": round(income_total - spent_total, 2),
                    "savings_rate": round(savings_rate, 1),
                },
                "period": period,
                "categoryMap": {str(k): v for k, v in CATEGORIES.items()},
                "skipLLM": skip_llm,
                "persona": persona,
            }

            invoke_resp = lambda_client.invoke(
                FunctionName=AI_LAMBDA_FUNCTION_NAME,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload, default=_json_default),
            )
            raw_result = json.loads(invoke_resp["Payload"].read() or "{}")

            if "body" in raw_result:
                result_body = raw_result["body"]
                if isinstance(result_body, str):
                    try:
                        ai_result = json.loads(result_body)
                    except Exception:
                        ai_result = {"error": "invalid ai body"}
                else:
                    ai_result = result_body
            else:
                ai_result = raw_result

            if not isinstance(ai_result, dict):
                return api_response(500, {"error": "AI returned invalid response"})

            meta = {
                "generated_at": datetime.utcnow().isoformat(),
                "data_sig": current_data_sig,
                "cache_key": ((ai_result.get("meta") or {}).get("cache_key") if isinstance(ai_result.get("meta"), dict) else None),
                "model": ((ai_result.get("meta") or {}).get("model_version") if isinstance(ai_result.get("meta"), dict) else BEDROCK_MODEL_ID),
                "cache_hit": False,
                "ttl_seconds": AI_CACHE_TTL_SECONDS,
            }

            cur.execute("DELETE FROM ai_insights WHERE user_id=%s AND related_period=%s", (user_id, period))
            cur.execute(
                "INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) VALUES (%s,%s,%s,%s)",
                (user_id, "__meta__", json.dumps(meta, default=_json_default), period),
            )
            cur.execute(
                "INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) VALUES (%s,%s,%s,%s)",
                (user_id, "__result__", json.dumps(ai_result, default=_json_default), period),
            )

            for insight in ai_result.get("insights", [])[:50]:
                cur.execute(
                    """
                    INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period, priority)
                    VALUES (%s,%s,%s,%s,%s)
                    """,
                    (
                        user_id,
                        insight.get("type", "insight"),
                        json.dumps(insight, default=_json_default),
                        period,
                        insight.get("priority", "MEDIUM"),
                    ),
                )

            conn.commit()
            ai_result["is_stale"] = False
            if not isinstance(ai_result.get("meta"), dict):
                ai_result["meta"] = {}
            ai_result["meta"]["cache_hit"] = False
            ai_result["meta"]["data_sig"] = current_data_sig
            return api_response(200, ai_result)
    except Exception as exc:
        logger.error(f"handle_ai_analyze failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Analysis failed"})
    finally:
        release_db_connection(conn)

def handle_smart_extract(user_id, body):
    """
    Optimized extraction using Bedrock.
    """
    body = body or {}
    text = body.get("text", "").strip()
    if not text:
        return api_response(400, {"error": "Text is required"})

    today = date.today().isoformat()
    cat_list = ",".join(CATEGORIES.values())

    normalized_text = re.sub(r"\s+", " ", text).strip()[:350]
    prompt = (
        f"Date:{today}; Input:{normalized_text}; Cats:{cat_list},Diğer. "
        "Return ONLY valid JSON with merchant_name,total_amount,receipt_date(YYYY-MM-DD),"
        "category_name,description. Use correct Turkish characters (ğ, ü, ş, ı, ö, ç). No markdown."
    )

    try:
        response = bedrock_runtime.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 300, "temperature": 0}
        )
        
        # Robust Parsing
        output_text = response["output"]["message"]["content"][0]["text"].strip()
        
        start = output_text.find("{")
        end = output_text.rfind("}")
        
        if start != -1 and end != -1 and end > start:
            json_str = output_text[start : end + 1]
            
            # Fix Trailing Commas (",}")
            json_str = re.sub(r',\s*}', '}', json_str)
            
            try:
                data = json.loads(json_str)
                return api_response(200, data)
            except json.JSONDecodeError as je:
                 # Fallback for simple dicts
                 try:
                     import ast
                     data = ast.literal_eval(json_str)
                     return api_response(200, data)
                 except:
                     logger.error(f"JSON Error: {je} | Raw: {json_str}")
                     return api_response(500, {"error": "Invalid JSON from AI", "raw": output_text})
        else:
            return api_response(500, {"error": "No JSON found", "raw": output_text})

    except Exception as e:
        logger.error(f"Smart extract failed: {e}")
        return api_response(500, {"error": str(e)})


def handle_dashboard(user_id):
    period = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(total_amount),0) AS total,
                       COALESCE(AVG(total_amount),0) AS avg_amount,
                       MAX(updated_at) AS last_upd
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                """,
                (user_id, period),
            )
            summary_row = cur.fetchone()

            cur.execute("SELECT COUNT(*) AS total_count FROM receipts WHERE user_id=%s", (user_id,))
            total_receipt_count = int(cur.fetchone()["total_count"])

            cur.execute(
                """
                SELECT category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY category_id
                """,
                (user_id, period),
            )
            category_rows = cur.fetchall()
            categories = {}
            for row in category_rows:
                categories[CATEGORIES.get(row.get("category_id"), "Diğer")] = round(_safe_float(row.get("total")), 2)

            cur.execute(
                """
                SELECT insight_type, insight_text
                FROM ai_insights
                WHERE user_id=%s AND related_period=%s AND insight_type IN ('__meta__','__result__')
                ORDER BY created_at DESC
                """,
                (user_id, period),
            )
            rows = cur.fetchall()

            meta = None
            saved_analysis = None
            for row in rows:
                if row["insight_type"] == "__meta__" and meta is None:
                    meta = row["insight_text"]
                if row["insight_type"] == "__result__" and saved_analysis is None:
                    saved_analysis = row["insight_text"]

            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = None
            if isinstance(saved_analysis, str):
                try:
                    saved_analysis = json.loads(saved_analysis)
                except Exception:
                    saved_analysis = None

            data_sig = _compute_data_signature(
                summary_row["total"],
                summary_row["count"],
                summary_row["last_upd"] or datetime.min,
            )

            is_stale = True
            if meta and isinstance(meta, dict):
                generated_at = meta.get("generated_at")
                saved_sig = meta.get("data_sig")
                if generated_at and saved_sig == data_sig:
                    try:
                        age_seconds = (datetime.utcnow() - datetime.fromisoformat(generated_at)).total_seconds()
                        if age_seconds <= 6 * 3600:
                            is_stale = False
                    except Exception:
                        is_stale = saved_sig != data_sig

            if isinstance(saved_analysis, dict):
                saved_analysis["is_stale"] = is_stale

            total_spent = round(_safe_float(summary_row["total"]), 2)
            avg_amount = round(_safe_float(summary_row["avg_amount"]), 2)
            count = int(summary_row["count"] or 0)

            # Get Incomes for the period
            cur.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM incomes WHERE user_id=%s AND TO_CHAR(income_date, 'YYYY-MM')=%s",
                (user_id, period)
            )
            income_row = cur.fetchone()
            total_income = round(_safe_float(income_row["total"]), 2)
            net_balance = total_income - total_spent

            # Get Top 3 Budgets (with spent + percentage)
            cur.execute("SELECT id, category_name, amount FROM budgets WHERE user_id=%s LIMIT 3", (user_id,))
            budget_rows_dash = cur.fetchall()
            cur.execute(
                """
                SELECT category_id, SUM(total_amount) AS spent
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY category_id
                """,
                (user_id, period),
            )
            spent_dash = cur.fetchall()
            spent_dash_map = {CATEGORIES.get(r["category_id"], "Diğer"): _safe_float(r["spent"]) for r in spent_dash}
            budgets = []
            for b in budget_rows_dash:
                cat = b.get("category_name")
                lim = _safe_float(b.get("amount"), 0.0)
                sp = spent_dash_map.get(cat, 0.0)
                pct = round((sp / lim) * 100, 1) if lim > 0 else 0.0
                budgets.append({"id": str(b.get("id", "")), "category_name": cat, "amount": lim, "spent": sp, "percentage": pct})

            # Get Top 3 Subscriptions
            cur.execute("SELECT name, amount, next_payment_date FROM subscriptions WHERE user_id=%s ORDER BY next_payment_date ASC LIMIT 3", (user_id,))
            subscriptions = cur.fetchall()

            cur.execute(
                """
                SELECT COUNT(*) FILTER (WHERE status='active') AS active_count,
                       COUNT(*) FILTER (WHERE status='completed') AS completed_count,
                       COALESCE(SUM(target_amount) FILTER (WHERE status='active'), 0) AS active_target_total,
                       COALESCE(SUM(current_amount) FILTER (WHERE status='active'), 0) AS active_current_total
                FROM financial_goals
                WHERE user_id=%s
                """,
                (user_id,),
            )
            goals = cur.fetchone() or {}

            active_target_total = _safe_float(goals.get("active_target_total"), 0.0)
            active_current_total = _safe_float(goals.get("active_current_total"), 0.0)
            goal_progress_pct = round((active_current_total / active_target_total) * 100, 1) if active_target_total > 0 else 0.0

            return api_response(
                200,
                {
                    "period": period,
                    "total_spent": total_spent,
                    "total_income": total_income,
                    "net_balance": net_balance,
                    "avg_amount": avg_amount,
                    "total_receipt_count": total_receipt_count,
                    "categories": categories,
                    "budgets": budgets,
                    "subscriptions": subscriptions,
                    "goals_summary": {
                        "active_count": int(goals.get("active_count") or 0),
                        "completed_count": int(goals.get("completed_count") or 0),
                        "active_target_total": round(active_target_total, 2),
                        "active_current_total": round(active_current_total, 2),
                        "active_progress_pct": goal_progress_pct,
                    },
                    "currency": "TRY",
                    "is_stale": is_stale,
                    "saved_analysis": saved_analysis,
                    "summary": {
                        "total": total_spent,
                        "count": count,
                        "currency": "TRY",
                    },
                },
            )
    finally:
        release_db_connection(conn)


def handle_incomes(user_id, method, body, income_id=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if method == "GET":
                cur.execute(
                    "SELECT id, source, amount, income_date, description, created_at FROM incomes WHERE user_id=%s ORDER BY income_date DESC, created_at DESC",
                    (user_id,),
                )
                return api_response(200, {"data": cur.fetchall()})

            if method == "POST":
                body = body or {}
                source = str(body.get("source") or "").strip()
                amount = _safe_float(body.get("amount"), None)
                income_date = body.get("income_date") or date.today().isoformat()
                description = str(body.get("description") or "").strip()

                if not source or amount is None or amount <= 0:
                    return api_response(400, {"error": "source and valid amount are required"})

                cur.execute(
                    """
                    INSERT INTO incomes (user_id, source, amount, income_date, description)
                    VALUES (%s,%s,%s,%s,%s)
                    RETURNING id, source, amount, income_date, description, created_at
                    """,
                    (user_id, source, amount, income_date, description),
                )
                created = cur.fetchone()
                conn.commit()
                return api_response(201, created)

            if method in {"PUT", "PATCH"} and income_id:
                body = body or {}
                cur.execute(
                    "SELECT id FROM incomes WHERE id=%s AND user_id=%s",
                    (income_id, user_id),
                )
                if not cur.fetchone():
                    return api_response(404, {"error": "Income not found"})

                source = str(body.get("source") or "").strip()
                amount = _safe_float(body.get("amount"), None)
                income_date = body.get("income_date")
                description = str(body.get("description") or "").strip()

                if not source or amount is None or amount <= 0:
                    return api_response(400, {"error": "source and valid amount are required"})

                cur.execute(
                    """
                    UPDATE incomes
                    SET source=%s, amount=%s, income_date=%s, description=%s
                    WHERE id=%s AND user_id=%s
                    RETURNING id, source, amount, income_date, description, created_at
                    """,
                    (source, amount, income_date, description, income_id, user_id),
                )
                updated = cur.fetchone()
                conn.commit()
                return api_response(200, updated)

            if method == "DELETE" and income_id:
                cur.execute("DELETE FROM incomes WHERE id=%s AND user_id=%s", (income_id, user_id))
                conn.commit()
                return api_response(200, {"message": "Deleted"})

            return api_response(400, {"error": "Invalid request"})
    finally:
        release_db_connection(conn)


def handle_export_data(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT receipt_date, merchant_name, total_amount, category_id, status
                FROM receipts
                WHERE user_id=%s
                ORDER BY COALESCE(receipt_date, created_at) DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Merchant", "Amount", "Category", "Status"])
        for row in rows:
            writer.writerow(
                [
                    row.get("receipt_date"),
                    row.get("merchant_name"),
                    _safe_float(row.get("total_amount")),
                    CATEGORIES.get(row.get("category_id"), "Diğer"),
                    row.get("status"),
                ]
            )

        key = f"exports/{user_id}/{uuid.uuid4()}.csv"
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=key, Body=output.getvalue().encode("utf-8"), ContentType="text/csv")
        download_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": key},
            ExpiresIn=600,
        )
        return api_response(200, {"download_url": download_url, "key": key})
    finally:
        release_db_connection(conn)


def handle_chart_data(user_id, params):
    params = params or {}
    rng = params.get("range", "1m")  # 1w, 1m, 3m, 6m, 1y
    group_type = params.get("type", "total") # total, category
    
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            interval_map = {
                "1w": "7 days",
                "1m": "1 month",
                "3m": "3 months",
                "6m": "6 months",
                "1y": "1 year"
            }
            db_interval = interval_map.get(rng, "1 month")
            is_daily = rng in ["1w", "1m"]
            date_format = "YYYY-MM-DD" if is_daily else "YYYY-MM"
            
            if group_type == "category":
                # Returns data: [{date_label, category, total}, ...]
                cur.execute(
                    f"""
                    SELECT TO_CHAR(receipt_date, %s) as date_label,
                           category_id,
                           SUM(total_amount) as total
                    FROM receipts
                    WHERE user_id=%s 
                      AND status != 'deleted' 
                      AND receipt_date >= DATE(NOW()) - INTERVAL %s
                    GROUP BY 1, 2
                    ORDER BY 1 ASC
                    """,
                    (date_format, user_id, db_interval)
                )
                rows = cur.fetchall()
                # Enrich with category names
                for row in rows:
                    row["category_name"] = CATEGORIES.get(row.get("category_id"), "Diğer")
                
                return api_response(200, {"data": rows, "range": rng, "type": "category", "is_daily": is_daily})
            
            else:
                # Total Trend
                cur.execute(
                    f"""
                    SELECT TO_CHAR(receipt_date, %s) as date_label,
                           SUM(total_amount) as total
                    FROM receipts
                    WHERE user_id=%s 
                      AND status != 'deleted' 
                      AND receipt_date >= DATE(NOW()) - INTERVAL %s
                    GROUP BY 1
                    ORDER BY 1 ASC
                    """,
                    (date_format, user_id, db_interval)
                )
                rows = cur.fetchall()
                return api_response(200, {"data": rows, "range": rng, "type": "total", "is_daily": is_daily})
    finally:
        release_db_connection(conn)


def handle_reports_detailed(user_id, params):
    params = params or {}
    # Default to current month if not specified
    now = datetime.now()
    month_str = params.get("month", now.strftime("%Y-%m")) # YYYY-MM
    
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Basic Monthly Stats
            cur.execute(
                """
                SELECT COUNT(*) as count, 
                       COALESCE(SUM(total_amount), 0) as total,
                       COALESCE(AVG(total_amount), 0) as avg
                FROM receipts 
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                """,
                (user_id, month_str)
            )
            stats = cur.fetchone()

            # 2. Highest Transaction of the Month
            cur.execute(
                """
                SELECT merchant_name, total_amount, receipt_date, category_id 
                FROM receipts 
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                ORDER BY total_amount DESC LIMIT 1
                """,
                (user_id, month_str)
            )
            highest = cur.fetchone()
            if highest:
                highest["category_name"] = CATEGORIES.get(highest["category_id"], "Diğer")

            # 3. Weekday vs Weekend Analysis (Proactive)
            # 0=Sunday, 6=Saturday in Postgres extract(dow)
            cur.execute(
                """
                SELECT 
                    CASE WHEN EXTRACT(DOW FROM receipt_date) IN (0, 6) THEN 'Hafta Sonu' ELSE 'Hafta İçi' END as day_type,
                    COUNT(*) as count,
                    SUM(total_amount) as total
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY 1
                """,
                (user_id, month_str)
            )
            day_analysis = cur.fetchall()

            # 4. Category Breakdown
            cur.execute(
                """
                SELECT category_id, SUM(total_amount) as total, COUNT(*) as count
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY 1
                ORDER BY total DESC
                """,
                (user_id, month_str)
            )
            cat_rows = cur.fetchall()
            categories_data = []
            for row in cat_rows:
                categories_data.append({
                    "name": CATEGORIES.get(row["category_id"], "Diğer"),
                    "value": float(row["total"]),
                    "count": int(row["count"])
                })

            # 5. Last 6 Months Trend (Total) for context
            cur.execute(
                """
                SELECT TO_CHAR(receipt_date, 'YYYY-MM') as month, SUM(total_amount) as total
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' 
                  AND receipt_date >= (TO_DATE(%s, 'YYYY-MM') - INTERVAL '5 months')
                  AND receipt_date < (TO_DATE(%s, 'YYYY-MM') + INTERVAL '1 month')
                GROUP BY 1 ORDER BY 1 ASC
                """,
                (user_id, month_str, month_str)
            )
            trend = cur.fetchall()

            return api_response(200, {
                "period": month_str,
                "stats": {
                    "total": float(stats["total"]),
                    "count": int(stats["count"]),
                    "avg": float(stats["avg"])
                },
                "highest_expense": highest,
                "day_analysis": day_analysis,
                "category_breakdown": categories_data,
                "trend": trend
            })
    finally:
        release_db_connection(conn)


def handle_reports_ai_summary(user_id, params):
    params = params or {}
    month_str = params.get("month", datetime.now().strftime("%Y-%m"))

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(total_amount), 0) AS total,
                       COALESCE(AVG(total_amount), 0) AS avg
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                """,
                (user_id, month_str),
            )
            stats = cur.fetchone() or {"count": 0, "total": 0, "avg": 0}

            count = int(stats.get("count") or 0)
            total = _safe_float(stats.get("total"), 0.0)
            avg = _safe_float(stats.get("avg"), 0.0)

            cur.execute(
                """
                SELECT category_id, SUM(total_amount) AS total, COUNT(*) AS count
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY category_id
                ORDER BY total DESC
                LIMIT 3
                """,
                (user_id, month_str),
            )
            category_rows = cur.fetchall()

            cur.execute(
                """
                SELECT COALESCE(merchant_name, 'Bilinmeyen') AS merchant,
                       COUNT(*) AS tx_count,
                       SUM(total_amount) AS total,
                       AVG(total_amount) AS avg_amount
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY 1
                ORDER BY tx_count DESC, total DESC
                LIMIT 5
                """,
                (user_id, month_str),
            )
            merchant_rows = cur.fetchall()

            cur.execute(
                """
                SELECT id, merchant_name, total_amount, receipt_date, category_id
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                ORDER BY total_amount DESC
                LIMIT 2
                """,
                (user_id, month_str),
            )
            highest_rows = cur.fetchall()

            cur.execute(
                """
                SELECT CASE WHEN EXTRACT(DOW FROM receipt_date) IN (0,6) THEN 'weekend' ELSE 'weekday' END AS day_type,
                       COUNT(*) AS count,
                       COALESCE(SUM(total_amount), 0) AS total
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY 1
                """,
                (user_id, month_str),
            )
            day_rows = cur.fetchall()

            cur.execute(
                """
                SELECT TO_CHAR(receipt_date, 'YYYY-MM') AS month,
                       COALESCE(SUM(total_amount), 0) AS total
                FROM receipts
                WHERE user_id=%s
                  AND status != 'deleted'
                  AND receipt_date >= (TO_DATE(%s, 'YYYY-MM') - INTERVAL '1 month')
                  AND receipt_date < (TO_DATE(%s, 'YYYY-MM') + INTERVAL '1 month')
                GROUP BY 1
                ORDER BY 1 ASC
                """,
                (user_id, month_str, month_str),
            )
            month_compare_rows = cur.fetchall()

            weekend_total = 0.0
            weekday_total = 0.0
            for r in day_rows:
                if r.get("day_type") == "weekend":
                    weekend_total = _safe_float(r.get("total"), 0.0)
                else:
                    weekday_total = _safe_float(r.get("total"), 0.0)

            risk_score = 20
            if avg > 0 and total > (avg * count * 1.05):
                risk_score += 10
            if weekend_total > weekday_total and weekend_total > 0:
                risk_score += 20
            if count > 0 and highest_rows:
                top_amt = _safe_float(highest_rows[0].get("total_amount"), 0.0)
                if avg > 0 and top_amt >= avg * 2.2:
                    risk_score += 25
            if count >= 20:
                risk_score += 10
            risk_score = int(max(0, min(100, risk_score)))

            current_month_total = total
            prev_month_total = 0.0
            for row in month_compare_rows:
                m = row.get("month")
                if m == month_str:
                    current_month_total = _safe_float(row.get("total"), current_month_total)
                else:
                    prev_month_total = _safe_float(row.get("total"), prev_month_total)

            trend_pct = 0.0
            if prev_month_total > 0:
                trend_pct = ((current_month_total - prev_month_total) / prev_month_total) * 100

            top_category = category_rows[0] if category_rows else None
            top_category_name = CATEGORIES.get((top_category or {}).get("category_id"), "Diğer") if top_category else "Belirsiz"

            monthly_summary = (
                f"{month_str} döneminde toplam {_safe_float(total):.0f} TL harcama ve {count} işlem kaydı var. "
                f"En baskın kategori: {top_category_name}."
            )
            if prev_month_total > 0:
                direction = "artış" if trend_pct > 0 else "düşüş"
                monthly_summary += f" Bir önceki aya göre %{abs(trend_pct):.1f} {direction} gözleniyor."

            critical_events = []
            for idx, row in enumerate(highest_rows, start=1):
                amount = _safe_float(row.get("total_amount"), 0.0)
                critical_events.append(
                    {
                        "id": f"high_{idx}",
                        "type": "high_spend",
                        "title": f"Yüksek harcama: {amount:.0f} TL",
                        "merchant": row.get("merchant_name") or "Bilinmeyen",
                        "amount": amount,
                        "date": row.get("receipt_date"),
                        "category": CATEGORIES.get(row.get("category_id"), "Diğer"),
                        "reason": "Aylık en yüksek tutarlı işlemler arasında.",
                        "confidence": 90,
                    }
                )

            merchant_frequency = []
            for row in merchant_rows:
                merchant_frequency.append(
                    {
                        "merchant": row.get("merchant") or "Bilinmeyen",
                        "tx_count": int(row.get("tx_count") or 0),
                        "total": _safe_float(row.get("total"), 0.0),
                        "avg_amount": _safe_float(row.get("avg_amount"), 0.0),
                    }
                )

            category_comments = []
            for row in category_rows[:3]:
                cat_total = _safe_float(row.get("total"), 0.0)
                pct = (cat_total / total * 100) if total > 0 else 0
                category_comments.append(
                    {
                        "category": CATEGORIES.get(row.get("category_id"), "Diğer"),
                        "comment": f"Bu kategoride {int(row.get('count') or 0)} işlem ile toplam {cat_total:.0f} TL (%{pct:.1f}) harcandı.",
                        "confidence": 88,
                    }
                )

            what_if = []
            if top_category:
                tc_total = _safe_float(top_category.get("total"), 0.0)
                for ratio in (0.1, 0.15):
                    save = round(tc_total * ratio, 2)
                    what_if.append(
                        {
                            "title": f"{top_category_name} kategorisinde %{int(ratio*100)} azaltım",
                            "estimated_monthly_saving": save,
                            "reason": f"En büyük kategori payı buradan geliyor; küçük azaltım etkisi yüksek olur.",
                            "confidence": 80,
                        }
                    )

            response = {
                "month": month_str,
                "risk_score": risk_score,
                "monthly_summary": monthly_summary,
                "critical_events": critical_events,
                "merchant_frequency": merchant_frequency,
                "what_if": what_if,
                "category_comments": category_comments,
                "meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "confidence": 82 if count >= 8 else 65,
                    "input_stats": {
                        "transaction_count": count,
                        "total_spent": round(total, 2),
                        "weekend_total": round(weekend_total, 2),
                        "weekday_total": round(weekday_total, 2),
                    },
                },
            }

            return api_response(200, response)
    finally:
        release_db_connection(conn)


def handle_reports_ai_feedback(user_id, body):
    body = body or {}
    month = _parse_period(body.get("month"))
    feedback_type = str(body.get("feedback_type") or "").strip().lower()
    section = str(body.get("section") or "reports_ai_summary").strip()[:64]
    item_id = str(body.get("item_id") or "").strip()[:64]
    note = re.sub(r"\s+", " ", str(body.get("note") or "")).strip()[:280]

    if feedback_type not in {"useful", "not_useful"}:
        return api_response(400, {"error": "feedback_type must be useful or not_useful"})

    feedback_payload = {
        "month": month,
        "feedback_type": feedback_type,
        "section": section,
        "item_id": item_id,
        "note": note,
        "source": "reports",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period, priority)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    "__feedback__",
                    json.dumps(feedback_payload, default=_json_default),
                    month,
                    "LOW",
                ),
            )
            conn.commit()

        return api_response(200, {"message": "Feedback kaydedildi"})
    finally:
        release_db_connection(conn)


def ensure_tables_exist():
    """Creates core tables for non-production bootstrap environments."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_data (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    cognito_sub VARCHAR(255) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    full_name VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id BIGSERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    token_hash VARCHAR(255) NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    file_url TEXT NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    merchant_name VARCHAR(255),
                    receipt_date DATE,
                    total_amount DECIMAL(12, 2) DEFAULT 0.00,
                    currency VARCHAR(10) DEFAULT 'TRY',
                    tax_amount DECIMAL(12, 2) DEFAULT 0.00,
                    category_id INTEGER,
                    last_error TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS receipt_items (
                    id BIGSERIAL PRIMARY KEY,
                    receipt_id UUID NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
                    item_name VARCHAR(255),
                    quantity INTEGER DEFAULT 1,
                    unit_price DECIMAL(10, 2),
                    total_price DECIMAL(10, 2)
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS budgets (
                    id BIGSERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    category_name VARCHAR(100) NOT NULL,
                    amount DECIMAL(12, 2) NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, category_name)
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id BIGSERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    name VARCHAR(120) NOT NULL,
                    amount DECIMAL(12, 2) NOT NULL,
                    next_payment_date DATE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_insights (
                    id BIGSERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    insight_type VARCHAR(50) NOT NULL,
                    insight_text JSONB NOT NULL,
                    priority VARCHAR(20) DEFAULT 'MEDIUM',
                    related_period VARCHAR(7),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_goals (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    title VARCHAR(120) NOT NULL,
                    target_amount DECIMAL(12, 2) NOT NULL,
                    current_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
                    target_date DATE,
                    metric_type VARCHAR(40) NOT NULL DEFAULT 'savings',
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    notes VARCHAR(280),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_action_items (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    related_period VARCHAR(7) NOT NULL,
                    title VARCHAR(180) NOT NULL,
                    source_insight VARCHAR(64),
                    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    due_date DATE,
                    done_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, related_period, title)
                );
                """
            )

            cur.execute("""
                CREATE TABLE IF NOT EXISTS incomes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    source VARCHAR(255) NOT NULL,
                    amount DECIMAL(12, 2) NOT NULL,
                    income_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    description TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fixed_expense_groups (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    title VARCHAR(150) NOT NULL,
                    category_type VARCHAR(80) DEFAULT 'Diger',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fixed_expense_items (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    group_id UUID NOT NULL REFERENCES fixed_expense_groups(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    name VARCHAR(150) NOT NULL,
                    amount DECIMAL(12, 2) NOT NULL,
                    due_day SMALLINT NOT NULL CHECK (due_day BETWEEN 1 AND 31),
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fixed_expense_payments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    item_id UUID NOT NULL REFERENCES fixed_expense_items(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
                    payment_date DATE NOT NULL,
                    amount DECIMAL(12, 2) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'paid',
                    note VARCHAR(280),
                    source VARCHAR(40) DEFAULT 'manual',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (item_id, payment_date)
                );
                """
            )

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_incomes_user_date ON incomes(user_id, income_date);
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id, expires_at);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_receipts_user_date ON receipts(user_id, receipt_date);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_budgets_user ON budgets(user_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id, next_payment_date);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_insights_user_period ON ai_insights(user_id, related_period);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_goals_user_status ON financial_goals(user_id, status, target_date);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ai_actions_user_period ON ai_action_items(user_id, related_period, status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fixed_groups_user ON fixed_expense_groups(user_id, is_active);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fixed_items_group ON fixed_expense_items(group_id, is_active);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fixed_payments_item_date ON fixed_expense_payments(item_id, payment_date);")

            # Safe column additions for receipts (payment_method, description)
            cur.execute("""
                DO $$ BEGIN
                    ALTER TABLE receipts ADD COLUMN IF NOT EXISTS payment_method VARCHAR(40);
                    ALTER TABLE receipts ADD COLUMN IF NOT EXISTS description TEXT;
                EXCEPTION WHEN others THEN NULL;
                END $$;
            """)

            conn.commit()
    except Exception as e:
        logger.error(f"Table creation failed: {e}")
    finally:
        release_db_connection(conn)


def lambda_handler(event, context):
    # Optional runtime migration (disabled by default).
    maybe_run_migrations_once()

    try:
        method = event.get("httpMethod", "")
        path = (event.get("path") or "").rstrip("/") or "/"

        if method == "OPTIONS":
            return api_response(200, {})

        body = {}
        if event.get("body"):
            raw_body = event.get("body")
            if event.get("isBase64Encoded"):
                try:
                    raw_body = base64.b64decode(raw_body).decode("utf-8")
                except Exception:
                    pass
            try:
                body = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
            except Exception:
                body = {}

        if path == "/auth/login" and method == "POST":
            return handle_auth_login(body)
        if path == "/auth/register" and method == "POST":
            return handle_auth_register(body)
        if path == "/auth/refresh" and method == "POST":
            return handle_auth_refresh(body)

        auth_header = _get_header(event.get("headers") or {}, "Authorization")
        token = auth_header.replace("Bearer ", "").replace("bearer ", "")
        claims = verify_jwt(token)
        if not claims:
            return api_response(401, {"error": "Unauthorized"})

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM user_data WHERE cognito_sub = %s", (claims.get("sub"),))
                row = cur.fetchone()
                if row:
                    user_id = row[0]
                else:
                    user = _ensure_user_record(claims)
                    user_id = user["id"]
        finally:
            release_db_connection(conn)

        if path == "/auth/me" and method == "GET":
            return handle_auth_me(user_id)
        if path == "/dashboard" and method == "GET":
            return handle_dashboard(user_id)
        if path == "/analyze" and method == "POST":
            return handle_ai_analyze(user_id, body)
        if path == "/receipts" and method == "GET":
            return handle_receipts_list(user_id, event.get("queryStringParameters") or {})
        if path == "/receipts/manual" and method == "POST":
            return handle_manual_receipt_create(user_id, body)
        if path == "/receipts/upload" and method == "POST":
            return handle_upload_init(user_id, body)
        if path == "/receipts/smart-extract" and method == "POST":
            return handle_smart_extract(user_id, body)
        if path == "/fixed-expenses" and method == "GET":
            return handle_fixed_expenses_get(user_id, event.get("queryStringParameters") or {})
        if path == "/fixed-expenses/groups" and method == "POST":
            return handle_fixed_expense_group_create(user_id, body)
        if path.startswith("/fixed-expenses/groups/"):
            parts = path.split("/")
            group_id = parts[3] if len(parts) > 3 and parts[3] else None
            if group_id:
                if method == "PUT":
                    return handle_fixed_expense_group_update(user_id, group_id, body)
                if method == "DELETE":
                    return handle_fixed_expense_group_delete(user_id, group_id)
        if path == "/fixed-expenses/items" and method == "POST":
            return handle_fixed_expense_item_create(user_id, body)
        if path.startswith("/fixed-expenses/items/"):
            parts = path.split("/")
            item_id = parts[3] if len(parts) > 3 and parts[3] else None
            if item_id:
                if len(parts) > 4 and parts[4] in {"payment", "payments"} and method == "POST":
                    return handle_fixed_expense_payment_upsert(user_id, item_id, body)
                if method == "PUT":
                    return handle_fixed_expense_item_update(user_id, item_id, body)
                if method == "DELETE":
                    return handle_fixed_expense_item_delete(user_id, item_id)
        if path == "/budgets":
            if method == "GET":
                return handle_get_budgets(user_id)
            if method == "POST":
                return handle_set_budget(user_id, body)
        if path.startswith("/budgets/"):
            budget_id = path.split("/")[2] if len(path.split("/")) > 2 else None
            if budget_id and method == "DELETE":
                return handle_delete_budget(user_id, budget_id)
        if path.startswith("/subscriptions"):
            parts = path.split("/")
            sub_id = parts[2] if len(parts) > 2 and parts[2] else None
            return handle_subscriptions(user_id, method, body, sub_id)
        if path == "/goals":
            if method in {"GET", "POST"}:
                return handle_goals(user_id, method, body)
        if path.startswith("/goals/"):
            parts = path.split("/")
            goal_id = parts[2] if len(parts) > 2 and parts[2] else None
            if goal_id and method in {"PUT", "DELETE"}:
                return handle_goals(user_id, method, body, goal_id)
        if path == "/insights/overview" and method == "GET":
            return handle_insights_overview(user_id, event.get("queryStringParameters") or {})
        if path == "/insights/what-if" and method == "GET":
            return handle_insights_what_if(user_id, event.get("queryStringParameters") or {})
        if path == "/ai-actions":
            if method == "GET":
                return handle_ai_actions(user_id, method, body, None, event.get("queryStringParameters") or {})
            if method == "POST":
                return handle_ai_actions(user_id, method, body, None, event.get("queryStringParameters") or {})
        if path.startswith("/ai-actions/"):
            parts = path.split("/")
            action_id = parts[2] if len(parts) > 2 and parts[2] else None
            if action_id and len(parts) > 3 and parts[3] == "apply" and method == "POST":
                return handle_ai_action_apply(user_id, action_id, body)
            if action_id and method in {"PUT", "PATCH", "DELETE"}:
                return handle_ai_actions(user_id, method, body, action_id, event.get("queryStringParameters") or {})
        if path == "/export" and method == "GET":
            return handle_export_data(user_id)
        if path == "/reports/summary" and method == "GET":
            return handle_reports_summary(user_id, event.get("queryStringParameters") or {})

        if path.startswith("/receipts/"):
            parts = path.split("/")
            if len(parts) >= 3:
                receipt_id = parts[2]
                if len(parts) > 3 and parts[3] == "process" and method == "POST":
                    return handle_receipt_process(user_id, receipt_id)
                # Receipt items CRUD:  /receipts/:id/items  or  /receipts/:id/items/:itemId
                if len(parts) > 3 and parts[3] == "items":
                    item_id = parts[4] if len(parts) > 4 and parts[4] else None
                    return handle_receipt_items(user_id, receipt_id, method, body, item_id)
                if method == "GET":
                    return handle_receipt_detail(user_id, receipt_id)
                if method == "PUT":
                    return handle_receipt_update(user_id, receipt_id, body)
                if method == "DELETE":
                    return handle_receipt_delete(user_id, receipt_id)

        if path == "/incomes" or path.startswith("/incomes/"):
            income_id = None
            parts = path.split("/")
            if len(parts) > 2:
                income_id = parts[2]
            return handle_incomes(user_id, method, body, income_id)

        if path == "/reports/chart" and method == "GET":
            return handle_chart_data(user_id, event.get("queryStringParameters"))

        if path == "/reports/detailed" and method == "GET":
            return handle_reports_detailed(user_id, event.get("queryStringParameters"))

        if path == "/reports/ai-summary" and method == "GET":
            return handle_reports_ai_summary(user_id, event.get("queryStringParameters") or {})

        if path == "/reports/ai-feedback" and method == "POST":
            return handle_reports_ai_feedback(user_id, body)

        return api_response(404, {"error": "Endpoint not found"})
    except Exception as exc:
        logger.error(f"FATAL: {exc}", exc_info=True)
        return api_response(500, {"error": "Internal server error"})


