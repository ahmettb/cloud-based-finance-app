"""
lambda_function.py — AI Lambda Entry Point
===========================================
AWS Lambda handler. backend_lambda'dan boto3.invoke() ile cagirilir.
DB erisimi YOKTUR — JSON alir, analiz yapar, JSON doner.

AWS Handler: lambda_function.lambda_handler

Moduler Yapi:
  lambda_function.py    <- bu dosya (entry point)
  ai_config.py          <- logger, env vars, Bedrock client
  ai_utils.py           <- saf yardimci fonksiyonlar
  anomaly_detector.py   <- AnomalyDetector class
  forecast_engine.py    <- ForecastEngine class
  pattern_miner.py      <- PatternMiner class
  insight_builder.py    <- InsightBuilder class
  llm_enricher.py       <- LLMEnricher + Claude entegrasyonu
  orchestrator.py       <- run_analysis() + health score

Structured Log Alanlari (her satirda):
  lambda_name  -> "ai"
  request_id   -> Lambda invocation ID
  user_id      -> Hangi kullanicinin analizi (payload'dan gelir)
  module_name  -> Logu ureten modul
  step         -> Analiz adimi (start, anomaly_detection, llm_start, ...)
  elapsed_ms   -> Adim suresi (ms)
  period       -> Analiz periyodu

CloudWatch Logs Insights — kullaniciya ozel debug:
  fields @timestamp, message, step, elapsed_ms
  | filter lambda_name="ai" and user_id="42"
  | sort @timestamp desc
"""

import json
import time
from datetime import datetime

from ai_config import logger, log_ctx
from orchestrator import run_analysis


# ══════════════════════════════════════════════════════════════════
#  Lambda Handler
# ══════════════════════════════════════════════════════════════════

def lambda_handler(event: dict, context) -> dict:
    """
    Entry point. Backend'den boto3.invoke() ile cagirilir.
    event = JSON payload (monthlyTotals, transactions, budgets, ...)

    Request lifecycle loglari:
      1. INVOKED  — lambda acildi, request_id + user_id belli
      2. COMPLETE — basarili analiz, toplam sure
      3. ERROR    — hata, stack trace
    """
    request_id: str = (
        context.aws_request_id if context else "local"
    )
    start_time: float = time.time()

    # ── Payload Parse ─────────────────────────────────────────────
    try:
        if isinstance(event, str):
            payload = json.loads(event)
        elif isinstance(event, dict):
            payload = event
        else:
            payload = json.loads(event)
    except Exception:
        payload = {}

    # request_id her zaman payload'a eklenir (orchestrator loglarinda kullanilir)
    payload["requestId"] = request_id

    # user_id -> payload'dan cek (backend tarafindan eklenir)
    user_id = str(payload.get("userId", "-"))
    period = payload.get("period", "-")

    _ctx = log_ctx(
        request_id=request_id,
        user_id=user_id,
        module_name="lambda_function",
        period=period,
    )

    logger.info(
        "AI Lambda invoked",
        extra={
            **_ctx,
            "step": "invoked",
            "tx_count": len(payload.get("transactions", [])),
            "monthly_count": len(payload.get("monthlyTotals", [])),
        },
    )

    try:
        # ── Minimum Veri Kontrolu ─────────────────────────────────
        if not payload.get("monthlyTotals") and not payload.get("transactions"):
            logger.warning(
                "Insufficient data — returning empty analysis",
                extra={**_ctx, "step": "insufficient_data"},
            )
            return {
                "statusCode": 200,
                "body": {
                    "coach": {
                        "headline": "Analiz icin yeterli veri yok.",
                        "summary": "",
                        "focus_areas": [],
                    },
                    "insights": [],
                    "forecast": None,
                    "anomalies": [],
                    "patterns": {},
                    "next_actions": [],
                    "meta": {
                        "error": "insufficient_data",
                        "generated_at": datetime.utcnow().isoformat() + "Z",
                    },
                },
            }

        # ── Ana Analiz ────────────────────────────────────────────
        result = run_analysis(payload)

        elapsed_ms = int((time.time() - start_time) * 1000)
        result["meta"]["total_processing_ms"] = elapsed_ms

        logger.info(
            "AI Lambda completed successfully",
            extra={
                **_ctx,
                "step": "complete",
                "elapsed_ms": elapsed_ms,
                "insight_count": len(result.get("insights", [])),
                "anomaly_count": len(result.get("anomalies", [])),
                "health_score": result.get("health_score", {}).get("score"),
            },
        )

        return {"statusCode": 200, "body": result}

    except Exception as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "AI Lambda fatal error",
            extra={**_ctx, "step": "fatal_error", "elapsed_ms": elapsed_ms},
            exc_info=True,
        )
        return {
            "statusCode": 500,
            "body": {
                "error": str(exc),
                "meta": {
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "total_processing_ms": elapsed_ms,
                },
            },
        }
