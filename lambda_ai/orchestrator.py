"""
orchestrator.py — AI Analysis Orchestrator
===========================================
Tüm AI analiz adımlarını koordine eder:
  1) Anomali Tespiti     (AnomalyDetector)
  2) Tahmin              (ForecastEngine)
  3) Pattern Mining      (PatternMiner)
  4) Bütçe / Sağlık / Hedef Insight'ları (InsightBuilder)
  5) LLM Zenginleştirme  (LLMEnricher)
  6) Finansal Sağlık Skoru
  7) Sonraki Eylem Listesi

Her adım ayrı try/except içinde — bir hata diğerlerini durdurmuyor.
Her adım kullanıcıya ait request_id ve user_id ile loglanıyor.
"""

import hashlib
import json
import time
from datetime import datetime

from ai_config import BEDROCK_MODEL_ID, logger, log_ctx
from ai_utils import sf, clamp
from anomaly_detector import AnomalyDetector
from forecast_engine import ForecastEngine
from pattern_miner import PatternMiner
from insight_builder import InsightBuilder
from llm_enricher import LLMEnricher


# ══════════════════════════════════════════════════════════════════
#  Financial Health Score
# ══════════════════════════════════════════════════════════════════

def compute_health_score(
    financial_health: dict,
    budgets: list,
    anomalies: list,
    goals: list,
) -> dict:
    """
    Finansal sağlık skoru (0-100).
    Kullanıcıya tek bakışta durum özeti verir.

    Ağırlıklar:
      - Tasarruf oranı:  %30
      - Bütçeye uyum:    %25
      - Harcama trendi:  %20
      - Hedef ilerleme:  %15
      - Anomali yokluğu: %10
    """
    breakdown: dict = {}

    # 1) Tasarruf oranı
    savings_rate = sf(financial_health.get("savings_rate", 0))
    if savings_rate >= 20:
        s_score = 30
    elif savings_rate >= 10:
        s_score = 20
    elif savings_rate >= 0:
        s_score = 10
    else:
        s_score = 0
    breakdown["savings"] = s_score

    # 2) Bütçeye uyum
    if budgets:
        over_count = sum(1 for b in budgets if sf(b.get("pct", 0)) > 100)
        ratio = 1 - (over_count / len(budgets))
        b_score = int(25 * ratio)
    else:
        b_score = 12  # Bütçe yoksa orta puan
    breakdown["budget"] = b_score

    # 3) Harcama trendi
    period_net = sf(financial_health.get("period_net", 0))
    if period_net > 0:
        t_score = 20
    elif period_net >= -500:
        t_score = 10
    else:
        t_score = 0
    breakdown["trend"] = t_score

    # 4) Hedef ilerleme
    active_goals = [
        g
        for g in (goals or [])
        if str(g.get("status", "active")).lower() == "active"
    ]
    if active_goals:
        progresses = []
        for g in active_goals:
            target = sf(g.get("target_amount"))
            current = sf(g.get("current_amount"))
            if target > 0:
                progresses.append(min(current / target, 1.0))
        avg_prog = (sum(progresses) / len(progresses)) if progresses else 0.5
        g_score = int(15 * avg_prog)
    else:
        g_score = 8
    breakdown["goals"] = g_score

    # 5) Anomali yokluğu
    anom_count = len(anomalies) if anomalies else 0
    if anom_count == 0:
        a_score = 10
    elif anom_count <= 2:
        a_score = 5
    else:
        a_score = 0
    breakdown["anomalies"] = a_score

    score = clamp(sum(breakdown.values()), 0, 100)
    label = (
        "Mükemmel" if score >= 80
        else "İyi" if score >= 60
        else "Orta" if score >= 40
        else "Dikkat Gerekli"
    )

    return {"score": score, "label": label, "breakdown": breakdown}


# ══════════════════════════════════════════════════════════════════
#  Next Actions Builder
# ══════════════════════════════════════════════════════════════════

def build_next_actions(insights: list) -> list:
    """Insight kartlarından öncelikli aksiyon listesi çıkarır."""
    actions = []
    for card in insights:
        if card.get("actions"):
            for act in card["actions"][:2]:
                actions.append(
                    {
                        "title": (
                            act if isinstance(act, str) else act.get("description", "")
                        ),
                        "source_insight": card.get("id"),
                        "priority": card.get("priority", "MEDIUM"),
                        "due_in_days": 7 if card.get("priority") == "HIGH" else 14,
                    }
                )
        elif card.get("priority") == "HIGH":
            actions.append(
                {
                    "title": card.get("title", "Aksiyon gerekli"),
                    "source_insight": card.get("id"),
                    "priority": "HIGH",
                    "due_in_days": 7,
                }
            )

    seen: set = set()
    unique = []
    for a in actions:
        key = a["title"][:40]
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique[:8] if unique else [
        {
            "title": "Harcamalarınızı düzenli olarak gözden geçirin.",
            "source_insight": None,
            "priority": "MEDIUM",
            "due_in_days": 7,
        },
        {
            "title": "Aylık bütçe hedeflerinizi belirleyin.",
            "source_insight": None,
            "priority": "MEDIUM",
            "due_in_days": 14,
        },
        {
            "title": "Tasarruf hedefi oluşturup ilerlemenizi takip edin.",
            "source_insight": None,
            "priority": "LOW",
            "due_in_days": 14,
        },
    ]


# ══════════════════════════════════════════════════════════════════
#  Main Orchestrator
# ══════════════════════════════════════════════════════════════════

def run_analysis(payload: dict) -> dict:
    """
    Ana orkestrasyon fonksiyonu.

    Input:  Backend'den gelen JSON payload
    Output: Tam analiz sonucu JSON

    Her adım bağımsız try/except ile korunur.
    Her adımın başı ve sonu user_id + request_id ile loglanır.
    """
    request_id = payload.get("requestId", "unknown")
    user_id = payload.get("userId", "-")
    period = payload.get("period", datetime.now().strftime("%Y-%m"))
    input_skip_llm = payload.get("skipLLM", False)

    # Temel context — tüm bu fonksiyonun loglarında kullanılır
    _ctx = log_ctx(
        request_id=request_id,
        user_id=user_id,
        module_name="orchestrator",
        period=period,
    )

    # Payload verileri
    monthly_totals = payload.get("monthlyTotals", [])
    transactions = payload.get("transactions", [])
    budgets = payload.get("budgets", [])
    subscriptions = payload.get("subscriptions", [])
    goals = payload.get("goals", [])
    financial_health = payload.get("financialHealth", {})
    merchant_stats = payload.get("merchantStats", [])
    persona = payload.get("persona", "friendly")

    auto_skip_llm = len(transactions) < 6 and len(monthly_totals) < 2
    skip_llm = bool(input_skip_llm or auto_skip_llm)

    logger.info(
        "Analysis started",
        extra={
            **_ctx,
            "step": "start",
            "tx_count": len(transactions),
            "monthly_count": len(monthly_totals),
            "budget_count": len(budgets),
            "goal_count": len(goals),
            "skip_llm": skip_llm,
        },
    )

    all_insights: list = []
    all_patterns: dict = {}

    # ── STEP 1: Complex Anomaly Detection ─────────────────────────
    step_start = time.time()
    try:
        anomalies = AnomalyDetector.detect(transactions)
        elapsed = int((time.time() - step_start) * 1000)
        logger.info(
            f"Anomaly detection complete — {len(anomalies)} found",
            extra={**_ctx, "step": "anomaly_detection", "elapsed_ms": elapsed},
        )
        all_insights.extend(InsightBuilder.from_anomalies(anomalies, period))
    except Exception:
        logger.error(
            "Anomaly detection failed",
            extra={**_ctx, "step": "anomaly_detection"},
            exc_info=True,
        )
        anomalies = []

    # ── STEP 2: Forecasting ───────────────────────────────────────
    step_start = time.time()
    try:
        forecast = ForecastEngine.forecast(monthly_totals)
        elapsed = int((time.time() - step_start) * 1000)
        logger.info(
            f"Forecast complete — estimate={forecast.get('next_month_estimate', 0):.0f} TL trend={forecast.get('trend')}",
            extra={**_ctx, "step": "forecast", "elapsed_ms": elapsed},
        )
        all_insights.extend(InsightBuilder.from_forecast(forecast, period))
    except Exception:
        logger.error(
            "Forecast failed",
            extra={**_ctx, "step": "forecast"},
            exc_info=True,
        )
        forecast = {"next_month_estimate": 0, "trend": "stable", "confidence_score": 10}

    # ── STEP 3: Pattern Mining ────────────────────────────────────
    step_start = time.time()
    try:
        velocity = PatternMiner.spending_velocity(transactions, period)
        if velocity:
            all_patterns["velocity"] = velocity

        dow = PatternMiner.day_of_week_distribution(transactions)
        if dow:
            all_patterns["day_distribution"] = dow

        cat_corr = PatternMiner.category_correlation(monthly_totals)
        if cat_corr:
            all_patterns["category_correlation"] = cat_corr

        recurring = PatternMiner.recurring_payments(transactions)
        if recurring:
            all_patterns["recurring_payments"] = recurring

        cat_shifts = PatternMiner.category_shifts(monthly_totals)
        if cat_shifts:
            all_patterns["category_shifts"] = cat_shifts

        elapsed = int((time.time() - step_start) * 1000)
        logger.info(
            f"Pattern mining complete — {len(all_patterns)} pattern types",
            extra={**_ctx, "step": "pattern_mining", "elapsed_ms": elapsed},
        )
        all_insights.extend(InsightBuilder.from_patterns(all_patterns, period))
    except Exception:
        logger.error(
            "Pattern mining failed",
            extra={**_ctx, "step": "pattern_mining"},
            exc_info=True,
        )

    # ── STEP 4: Budget + Financial Health + Goal Insights ─────────
    try:
        all_insights.extend(InsightBuilder.from_budget_alerts(budgets))
    except Exception:
        logger.error(
            "Budget insights failed",
            extra={**_ctx, "step": "budget_insights"},
            exc_info=True,
        )

    try:
        all_insights.extend(InsightBuilder.from_financial_health(financial_health, goals))
    except Exception:
        logger.error(
            "Financial health insights failed",
            extra={**_ctx, "step": "health_insights"},
            exc_info=True,
        )

    # Financial health score
    health_score = compute_health_score(financial_health, budgets, anomalies, goals)

    # Sort: HIGH > MEDIUM > LOW
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_insights.sort(
        key=lambda c: priority_order.get(c.get("priority", "LOW"), 2)
    )

    # ── STEP 5: LLM Enrichment ────────────────────────────────────
    llm_obs: dict = {}
    if not skip_llm:
        step_start = time.time()
        try:
            all_insights, coach, llm_obs = LLMEnricher.enrich(
                period=period,
                insights=all_insights,
                forecast=forecast,
                patterns=all_patterns,
                persona=persona,
                request_id=request_id,
                user_id=user_id,
            )
            elapsed = int((time.time() - step_start) * 1000)
            logger.info(
                "LLM enrichment done",
                extra={**_ctx, "step": "llm_enrichment", "elapsed_ms": elapsed},
            )
        except Exception:
            logger.error(
                "LLM enrichment error",
                extra={**_ctx, "step": "llm_enrichment"},
                exc_info=True,
            )
            coach = LLMEnricher._fallback_coach(period, forecast)
    else:
        logger.info(
            "LLM skipped",
            extra={
                **_ctx,
                "step": "llm_skip",
                "reason": "cache_hit" if input_skip_llm else "insufficient_data",
            },
        )
        coach = LLMEnricher._fallback_coach(period, forecast)

    # ── Build Response ────────────────────────────────────────────
    next_actions = build_next_actions(all_insights)

    cache_input = json.dumps(
        {
            "period": period,
            "tx_count": len(transactions),
            "monthly_count": len(monthly_totals),
            "total": sum(sf(m.get("total")) for m in monthly_totals),
        },
        sort_keys=True,
    )
    cache_key = hashlib.md5(cache_input.encode()).hexdigest()[:16]

    response = {
        "coach": coach,
        "insights": all_insights[:12],
        "forecast": forecast,
        "anomalies": anomalies[:10],
        "patterns": all_patterns,
        "next_actions": next_actions,
        "financial_health": financial_health,
        "health_score": health_score,
        "goals_summary": {
            "active_count": len(
                [
                    g
                    for g in goals
                    if str(g.get("status", "active")).lower() == "active"
                ]
            ),
            "total_count": len(goals),
        },
        "meta": {
            "model_version": BEDROCK_MODEL_ID,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "analysis_version": "v8",
            "period": period,
            "cache_key": cache_key,
            "llm_observability": llm_obs,
            "input_stats": {
                "monthly_count": len(monthly_totals),
                "transaction_count": len(transactions),
                "budget_count": len(budgets),
                "goal_count": len(goals),
            },
        },
    }

    logger.info(
        "Analysis complete",
        extra={
            **_ctx,
            "step": "complete",
            "insight_count": len(all_insights),
            "anomaly_count": len(anomalies),
            "pattern_count": len(all_patterns),
            "health_score": health_score.get("score"),
        },
    )

    return response
