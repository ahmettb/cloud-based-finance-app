"""
lambda_function.py — Backend Lambda Entry Point
================================================
AWS Lambda handler. API Gateway'den gelen istekleri alır,
JWT doğrular, user_id çözümler ve ilgili route handler'ına yönlendirir.

Modüler Yapı:
  lambda_function.py   <- bu dosya (entry point, handler: lambda_function.lambda_handler)
  config.py            <- logger, env vars, AWS clients
  auth.py              <- kimlik doğrulama
  db.py                <- veritabanı bağlantısı
  helpers.py           <- yardımcı fonksiyonlar
  routes/
    receipts.py, budgets.py, dashboard.py, ...

Structured Log Alanları (her satırda):
  lambda_name   -> "backend"
  request_id    -> Lambda invocation ID (CloudWatch'ta otomatik gruplandırma)
  user_id       -> DB integer ID (kullanıcıya ait tüm logları filtrelemek için)
  cognito_sub   -> Cognito UUID
  method        -> HTTP metodu
  path          -> İstek yolu
  module_name   -> Logu üreten modül/route

CloudWatch Logs Insights — kullanıcıya özel debug sorgusu:
  fields @timestamp, message, user_id, method, path, elapsed_ms
  | filter lambda_name="backend" and user_id="42"
  | sort @timestamp desc
"""

import base64
import json
import time

from config import log_ctx, logger
from db import get_db_connection, maybe_run_migrations_once, release_db_connection
from helpers import _get_header, api_response

# ── Auth ──────────────────────────────────────────────────────────
from auth import (
    _ensure_user_record,
    handle_auth_confirm,
    handle_auth_login,
    handle_auth_me,
    handle_auth_refresh,
    handle_auth_register,
    verify_jwt,
)

# ── Route Handlers ────────────────────────────────────────────────
from routes.receipts import (
    handle_manual_receipt_create,
    handle_receipt_delete,
    handle_receipt_detail,
    handle_receipt_items,
    handle_receipt_process,
    handle_receipt_update,
    handle_receipts_list,
    handle_smart_extract,
    handle_upload_init,
)
from routes.budgets import (
    handle_delete_budget,
    handle_get_budgets,
    handle_set_budget,
)
from routes.subscriptions import handle_subscriptions
from routes.goals import handle_goals
from routes.incomes import handle_incomes
from routes.fixed_expenses import (
    handle_fixed_expense_group_create,
    handle_fixed_expense_group_delete,
    handle_fixed_expense_group_update,
    handle_fixed_expense_item_create,
    handle_fixed_expense_item_delete,
    handle_fixed_expense_item_update,
    handle_fixed_expense_payment_upsert,
    handle_fixed_expenses_get,
)
from routes.insights import (
    handle_ai_action_apply,
    handle_ai_actions,
    handle_ai_analyze,
    handle_insights_overview,
    handle_insights_what_if,
)
from routes.reports import (
    handle_chart_data,
    handle_reports_ai_feedback,
    handle_reports_ai_summary,
    handle_reports_detailed,
    handle_reports_summary,
)
from routes.dashboard import handle_dashboard
from routes.export import handle_export_data
from routes.chat import handle_ai_chat


# ══════════════════════════════════════════════════════════════════
#  Internal Helpers
# ══════════════════════════════════════════════════════════════════

def _parse_body(event: dict) -> dict:
    """Body'yi güvenli şekilde parse eder (base64 destekli)."""
    raw = event.get("body")
    if not raw:
        return {}
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            pass
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {}


def _extract_request_meta(event: dict) -> tuple:
    """HTTP method ve path'i çıkarır, /backend prefix'ini temizler."""
    method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method", "")
    )
    path = event.get("path") or event.get("rawPath") or "/"
    if path.startswith("/backend/"):
        path = path[len("/backend"):]
    return method, (path.rstrip("/") or "/")


def _resolve_user_id(claims: dict, request_id: str) -> tuple:
    """
    Cognito claims'ten DB user_id çözer.
    Returns: (user_id, cognito_sub)
    """
    cognito_sub = claims.get("sub", "-")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM user_data WHERE cognito_sub = %s",
                (cognito_sub,),
            )
            row = cur.fetchone()
            if row:
                return row[0], cognito_sub
            # Ilk giris — kullanici kaydi yarat
            user = _ensure_user_record(claims)
            logger.info(
                "New user record created",
                extra=log_ctx(
                    request_id=request_id,
                    user_id=user["id"],
                    cognito_sub=cognito_sub,
                    module_name="lambda_function",
                ),
            )
            return user["id"], cognito_sub
    finally:
        release_db_connection(conn)


# ══════════════════════════════════════════════════════════════════
#  Lambda Handler
# ══════════════════════════════════════════════════════════════════

def lambda_handler(event: dict, context) -> dict:
    """
    Tüm API isteklerinin giriş noktası.
    AWS Handler: lambda_function.lambda_handler

    Her istek şu şekilde loglanır:
      1) İstek geldiğinde  : method, path, request_id
      2) JWT sonrası       : user_id, cognito_sub eklenir
      3) Yanıt gönderilirken: elapsed_ms
      4) Hata durumunda    : exception_type, stack trace
    """
    maybe_run_migrations_once()

    request_id: str = getattr(context, "aws_request_id", "local")
    start_time: float = time.time()

    method, path = _extract_request_meta(event)

    # Temel istek logu — user_id henüz bilinmiyor
    logger.info(
        "Request received",
        extra=log_ctx(
            request_id=request_id,
            method=method,
            path=path,
            module_name="lambda_function",
        ),
    )

    try:
        # ── OPTIONS (CORS pre-flight) ──────────────────────────────
        if method == "OPTIONS":
            return api_response(200, {})

        body = _parse_body(event)
        qsp = event.get("queryStringParameters") or {}

        # ── Public Auth Endpoints (JWT gerekmez) ───────────────────
        _ctx = log_ctx(request_id=request_id, method=method, path=path, module_name="auth")

        if path == "/auth/login" and method == "POST":
            logger.info("Auth login attempt", extra=_ctx)
            return handle_auth_login(body)

        if path == "/auth/register" and method == "POST":
            logger.info("Auth register attempt", extra=_ctx)
            return handle_auth_register(body)

        if path == "/auth/confirm" and method == "POST":
            logger.info("Auth confirm attempt", extra=_ctx)
            return handle_auth_confirm(body)

        if path == "/auth/refresh" and method == "POST":
            logger.info("Auth token refresh", extra=_ctx)
            return handle_auth_refresh(body)

        # ── JWT Dogrulama ─────────────────────────────────────────
        auth_header = _get_header(event.get("headers") or {}, "Authorization")
        token = auth_header.replace("Bearer ", "").replace("bearer ", "")
        claims = verify_jwt(token)

        if not claims:
            logger.warning(
                "JWT verification failed — unauthorized",
                extra=log_ctx(
                    request_id=request_id,
                    method=method,
                    path=path,
                    module_name="lambda_function",
                ),
            )
            return api_response(401, {"error": "Unauthorized"})

        # ── User ID Çözümleme ──────────────────────────────────────
        user_id, cognito_sub = _resolve_user_id(claims, request_id)

        # Artik tüm loglar için tam context mevcut
        ctx = log_ctx(
            request_id=request_id,
            user_id=user_id,
            cognito_sub=cognito_sub,
            method=method,
            path=path,
            module_name="lambda_function",
        )

        logger.info("Request authenticated — routing", extra=ctx)

        # ── Protected Routes ───────────────────────────────────────

        if path == "/auth/me" and method == "GET":
            return handle_auth_me(user_id)

        if path == "/dashboard" and method == "GET":
            return handle_dashboard(user_id)

        if path == "/analyze" and method == "POST":
            return handle_ai_analyze(user_id, body)

        # Receipts
        if path == "/receipts" and method == "GET":
            return handle_receipts_list(user_id, qsp)
        if path == "/receipts/manual" and method == "POST":
            return handle_manual_receipt_create(user_id, body)
        if path == "/receipts/upload" and method == "POST":
            return handle_upload_init(user_id, body)
        if path == "/receipts/smart-extract" and method == "POST":
            return handle_smart_extract(user_id, body)

        if path.startswith("/receipts/"):
            parts = path.split("/")
            if len(parts) >= 3:
                receipt_id = parts[2]
                if len(parts) > 3 and parts[3] == "process" and method == "POST":
                    return handle_receipt_process(user_id, receipt_id)
                if len(parts) > 3 and parts[3] == "items":
                    item_id = parts[4] if len(parts) > 4 and parts[4] else None
                    return handle_receipt_items(user_id, receipt_id, method, body, item_id)
                if method == "GET":
                    return handle_receipt_detail(user_id, receipt_id)
                if method == "PUT":
                    return handle_receipt_update(user_id, receipt_id, body)
                if method == "DELETE":
                    return handle_receipt_delete(user_id, receipt_id)

        # Fixed Expenses
        if path == "/fixed-expenses" and method == "GET":
            return handle_fixed_expenses_get(user_id, qsp)
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

        # Budgets
        if path == "/budgets":
            if method == "GET":
                return handle_get_budgets(user_id)
            if method == "POST":
                return handle_set_budget(user_id, body)
        if path.startswith("/budgets/"):
            budget_id = path.split("/")[2] if len(path.split("/")) > 2 else None
            if budget_id and method == "DELETE":
                return handle_delete_budget(user_id, budget_id)

        # Subscriptions
        if path.startswith("/subscriptions"):
            parts = path.split("/")
            sub_id = parts[2] if len(parts) > 2 and parts[2] else None
            return handle_subscriptions(user_id, method, body, sub_id)

        # Goals
        if path == "/goals":
            if method in {"GET", "POST"}:
                return handle_goals(user_id, method, body)
        if path.startswith("/goals/"):
            parts = path.split("/")
            goal_id = parts[2] if len(parts) > 2 and parts[2] else None
            if goal_id and method in {"PUT", "DELETE"}:
                return handle_goals(user_id, method, body, goal_id)

        # Insights
        if path == "/insights/overview" and method == "GET":
            return handle_insights_overview(user_id, qsp)
        if path == "/insights/what-if" and method == "GET":
            return handle_insights_what_if(user_id, qsp)

        # AI Actions
        if path == "/ai-actions":
            if method in {"GET", "POST"}:
                return handle_ai_actions(user_id, method, body, None, qsp)
        if path.startswith("/ai-actions/"):
            parts = path.split("/")
            action_id = parts[2] if len(parts) > 2 and parts[2] else None
            if action_id and len(parts) > 3 and parts[3] == "apply" and method == "POST":
                return handle_ai_action_apply(user_id, action_id, body)
            if action_id and method in {"PUT", "PATCH", "DELETE"}:
                return handle_ai_actions(user_id, method, body, action_id, qsp)

        # Export
        if path == "/export" and method == "GET":
            return handle_export_data(user_id)

        # Reports
        if path == "/reports/summary" and method == "GET":
            return handle_reports_summary(user_id, qsp)
        if path == "/reports/chart" and method == "GET":
            return handle_chart_data(user_id, qsp)
        if path == "/reports/detailed" and method == "GET":
            return handle_reports_detailed(user_id, qsp)
        if path == "/reports/ai-summary" and method == "GET":
            return handle_reports_ai_summary(user_id, qsp)
        if path == "/reports/ai-feedback" and method == "POST":
            return handle_reports_ai_feedback(user_id, body)

        # Incomes
        if path == "/incomes" or path.startswith("/incomes/"):
            parts = path.split("/")
            income_id = parts[2] if len(parts) > 2 and parts[2] else None
            return handle_incomes(user_id, method, body, income_id)

        # Chat
        if path == "/chat" and method == "POST":
            return handle_ai_chat(user_id, body)

        # 404
        logger.warning(
            "Endpoint not found",
            extra=log_ctx(
                request_id=request_id,
                user_id=user_id,
                cognito_sub=cognito_sub,
                method=method,
                path=path,
                module_name="lambda_function",
            ),
        )
        return api_response(404, {"error": "Endpoint not found"})

    except Exception as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Unhandled exception in lambda_handler",
            extra=log_ctx(
                request_id=request_id,
                method=method,
                path=path,
                module_name="lambda_function",
                elapsed_ms=elapsed_ms,
            ),
            exc_info=True,
        )
        return api_response(500, {"error": "Internal server error"})
    finally:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Request completed",
            extra=log_ctx(
                request_id=request_id,
                method=method,
                path=path,
                module_name="lambda_function",
                elapsed_ms=elapsed_ms,
            ),
        )
