"""
lambda_function.py — AI Lambda Entry Point (Async Pattern)
===========================================================
Backend'den Event (async) invoke ile çağrılır.
Analiz tamamlanınca sonucu doğrudan DB'ye yazar.

Akış:
  1. Backend Lambda: InvocationType='Event' → anında döner
  2. AI Lambda: analizi arka planda yapar
  3. AI Lambda: sonucu DB'ye yazar (__result__ + __meta__)
  4. Frontend: GET /analyze ile poll eder → cache'den döner

AWS Handler: lambda_function.lambda_handler
"""

import json
import time
from datetime import datetime

from ai_config import (
    get_db_connection, logger, log_ctx, BEDROCK_MODEL_ID,
)
from orchestrator import run_analysis


# ══════════════════════════════════════════════════════════════════
#  DB Write Helper
# ══════════════════════════════════════════════════════════════════

def _save_result_to_db(user_id: str, period: str, data_sig: str, result: dict) -> None:
    """
    Analiz sonucunu ai_insights tablosuna yazar.
    Backend'in cache lookup mantığıyla uyumlu — aynı format.
    """
    import psycopg2.extras

    def _jdefault(o):
        if hasattr(o, "isoformat"):
            return o.isoformat()
        if hasattr(o, "item"):
            return o.item()
        return str(o)

    meta = {
        "generated_at": datetime.utcnow().isoformat(),
        "data_sig": data_sig,
        "cache_key": (result.get("meta") or {}).get("cache_key"),
        "model": (result.get("meta") or {}).get("model_version", BEDROCK_MODEL_ID),
        "cache_hit": False,
        "status": "done",
        "ttl_seconds": 21600,
    }
    meta_json = json.dumps(meta, default=_jdefault)
    result_json = json.dumps(result, default=_jdefault)

    conn = get_db_connection()
    with conn.cursor() as cur:
        # Eski kayıtları temizle
        cur.execute(
            "DELETE FROM ai_insights WHERE user_id=%s AND related_period=%s",
            (user_id, period),
        )
        # Meta kaydı
        cur.execute(
            "INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) "
            "VALUES (%s, '__meta__', %s, %s)",
            (user_id, meta_json, period),
        )
        # Sonuç kaydı
        cur.execute(
            "INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) "
            "VALUES (%s, '__result__', %s, %s)",
            (user_id, result_json, period),
        )
        # Bireysel insight kartları
        for insight in result.get("insights", [])[:50]:
            cur.execute(
                "INSERT INTO ai_insights "
                "(user_id, insight_type, insight_text, related_period, priority) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    user_id,
                    insight.get("type", "insight"),
                    json.dumps(insight, default=_jdefault),
                    period,
                    insight.get("priority", "MEDIUM"),
                ),
            )
    conn.commit()


def _save_processing_state(user_id: str, period: str, data_sig: str) -> None:
    """
    Analiz başladığında 'processing' durumunu DB'ye yazar.
    Frontend bu durumu görünce 'Analiz devam ediyor...' gösterir.
    """
    import json

    meta = {
        "generated_at": datetime.utcnow().isoformat(),
        "data_sig": data_sig,
        "status": "processing",
        "cache_hit": False,
    }
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM ai_insights WHERE user_id=%s AND related_period=%s",
            (user_id, period),
        )
        cur.execute(
            "INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) "
            "VALUES (%s, '__meta__', %s, %s)",
            (user_id, json.dumps(meta), period),
        )
    conn.commit()


# ══════════════════════════════════════════════════════════════════
#  Lambda Handler
# ══════════════════════════════════════════════════════════════════

def lambda_handler(event: dict, context) -> dict:
    """
    Async invoke entry point.
    1. DB'ye 'processing' yaz (frontend poll için)
    2. Analiz yap
    3. Sonucu DB'ye yaz
    4. Return (async invocation'da bu değer kullanılmaz)
    """
    request_id: str = context.aws_request_id if context else "local"
    start_time: float = time.time()

    # ── Payload Parse ─────────────────────────────────────────────
    try:
        payload = json.loads(event) if isinstance(event, str) else dict(event)
    except Exception:
        payload = {}

    payload["requestId"] = request_id
    user_id = str(payload.get("userId", "-"))
    period = payload.get("period", "-")
    data_sig = payload.get("dataSig", "unknown")

    _ctx = log_ctx(
        request_id=request_id,
        user_id=user_id,
        module_name="lambda_function",
        period=period,
    )

    logger.info(
        "AI Lambda invoked (async)",
        extra={
            **_ctx,
            "step": "invoked",
            "tx_count": len(payload.get("transactions", [])),
            "monthly_count": len(payload.get("monthlyTotals", [])),
        },
    )

    # ── Minimum Veri Kontrolü ─────────────────────────────────────
    if not payload.get("monthlyTotals") and not payload.get("transactions"):
        logger.warning(
            "Insufficient data — skipping analysis",
            extra={**_ctx, "step": "insufficient_data"},
        )
        empty = {
            "coach": {"headline": "Analiz icin yeterli veri yok.", "summary": "", "focus_areas": []},
            "insights": [], "forecast": None, "anomalies": [], "patterns": {},
            "next_actions": [],
            "meta": {"error": "insufficient_data", "generated_at": datetime.utcnow().isoformat() + "Z"},
        }
        try:
            _save_result_to_db(user_id, period, data_sig, empty)
        except Exception:
            logger.error("Failed to save empty result to DB", extra=_ctx, exc_info=True)
        return {"statusCode": 200}

    # ── DB'ye processing durumu yaz ───────────────────────────────
    try:
        _save_processing_state(user_id, period, data_sig)
        logger.info("Processing state written to DB", extra={**_ctx, "step": "processing_state"})
    except Exception:
        logger.warning(
            "Could not write processing state (continuing anyway)",
            extra=_ctx,
            exc_info=True,
        )

    # ── Ana Analiz ────────────────────────────────────────────────
    try:
        result = run_analysis(payload)
        elapsed_ms = int((time.time() - start_time) * 1000)
        result["meta"]["total_processing_ms"] = elapsed_ms

        logger.info(
            "AI analysis completed — saving to DB",
            extra={
                **_ctx,
                "step": "complete",
                "elapsed_ms": elapsed_ms,
                "insight_count": len(result.get("insights", [])),
                "anomaly_count": len(result.get("anomalies", [])),
                "health_score": result.get("health_score", {}).get("score"),
            },
        )

        _save_result_to_db(user_id, period, data_sig, result)
        logger.info("Results saved to DB", extra={**_ctx, "step": "db_saved"})
        return {"statusCode": 200}

    except Exception as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "AI Lambda fatal error",
            extra={**_ctx, "step": "fatal_error", "elapsed_ms": elapsed_ms},
            exc_info=True,
        )
        # Hata durumunda 'error' meta kaydı yaz — frontend uyarı gösterir
        try:
            error_result = {
                "coach": {
                    "headline": "Analiz sirasinda bir hata olustu.",
                    "summary": "Lutfen tekrar deneyin.",
                    "focus_areas": [],
                },
                "insights": [], "anomalies": [], "patterns": {}, "next_actions": [],
                "meta": {
                    "error": str(exc),
                    "status": "error",
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                },
            }
            _save_result_to_db(user_id, period, data_sig, error_result)
        except Exception:
            pass
        return {"statusCode": 500}
