import hashlib
import json
from datetime import date, datetime, timedelta

from psycopg2.extras import RealDictCursor

from config import (
    AI_CACHE_TTL_SECONDS, AI_LAMBDA_FUNCTION_NAME, BEDROCK_MODEL_ID,
    CATEGORIES, lambda_client, logger,
)
from db import get_db_connection, release_db_connection
from helpers import _json_default, _normalize_text, _parse_period, _period_bounds, _safe_float, api_response


def _compute_data_signature(total_amount, receipt_count, last_upd, persona="friendly"):
    raw = f"{_safe_float(total_amount)}-{int(receipt_count)}-{last_upd}-{persona}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _normalize_action_status(value, default="pending"):
    allowed = {"pending", "done", "dismissed"}
    candidate = str(value or default).strip().lower()
    return candidate if candidate in allowed else default


def _normalize_action_priority(value, default="MEDIUM"):
    allowed = {"HIGH", "MEDIUM", "LOW"}
    candidate = str(value or default).strip().upper()
    return candidate if candidate in allowed else default


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
                """SELECT COUNT(*) AS tx_count, COALESCE(SUM(total_amount), 0) AS total_spent
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date BETWEEN %s AND %s""",
                (user_id, period_start, period_end),
            )
            spending_row = cur.fetchone() or {"tx_count": 0, "total_spent": 0}
            cur.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total_income FROM incomes WHERE user_id=%s AND income_date BETWEEN %s AND %s",
                (user_id, period_start, period_end),
            )
            income_row = cur.fetchone() or {"total_income": 0}
            cur.execute("SELECT COALESCE(SUM(amount), 0) AS total_subscriptions FROM subscriptions WHERE user_id=%s", (user_id,))
            sub_row = cur.fetchone() or {"total_subscriptions": 0}
            cur.execute("SELECT COALESCE(SUM(amount), 0) AS total_fixed FROM fixed_expense_items WHERE user_id=%s AND is_active=TRUE", (user_id,))
            fixed_row = cur.fetchone() or {"total_fixed": 0}
            cur.execute("SELECT category_name, amount FROM budgets WHERE user_id=%s", (user_id,))
            budgets = cur.fetchall() or []
            cur.execute(
                """SELECT category_id, COALESCE(SUM(total_amount),0) AS spent
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date BETWEEN %s AND %s
                GROUP BY category_id""",
                (user_id, period_start, period_end),
            )
            spent_rows = cur.fetchall() or []
            spent_by_category = {
                CATEGORIES.get(r.get("category_id"), "Diger").lower(): _safe_float(r.get("spent"))
                for r in spent_rows
            }
            budgets_count = len(budgets)
            met_count = sum(1 for b in budgets
                if _safe_float(b.get("amount"), 0.0) > 0
                and spent_by_category.get(str(b.get("category_name") or "").strip().lower(), 0.0) <= _safe_float(b.get("amount"), 0.0))
            cur.execute(
                """SELECT category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date BETWEEN %s AND %s
                GROUP BY category_id ORDER BY total DESC LIMIT 4""",
                (user_id, period_start, period_end),
            )
            top_rows = cur.fetchall() or []
            cur.execute(
                """SELECT COUNT(*) FILTER (WHERE status='active') AS active_count,
                       COUNT(*) FILTER (WHERE status='completed') AS completed_count,
                       COALESCE(SUM(target_amount) FILTER (WHERE status='active'), 0) AS active_target_total,
                       COALESCE(SUM(current_amount) FILTER (WHERE status='active'), 0) AS active_current_total
                FROM financial_goals WHERE user_id=%s""",
                (user_id,),
            )
            goals_row = cur.fetchone() or {}
            cur.execute(
                """SELECT id, title, target_date, target_amount, current_amount, status
                FROM financial_goals
                WHERE user_id=%s AND status='active' AND target_date IS NOT NULL
                  AND target_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '14 days')
                ORDER BY target_date ASC LIMIT 5""",
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
            top_categories = [{"name": CATEGORIES.get(r.get("category_id"), "Diger"), "total": round(_safe_float(r.get("total")), 2)} for r in top_rows]
            active_target_total = _safe_float(goals_row.get("active_target_total"), 0.0)
            active_current_total = _safe_float(goals_row.get("active_current_total"), 0.0)
            goal_progress_pct = round((active_current_total / active_target_total) * 100, 1) if active_target_total > 0 else 0.0
            return api_response(200, {
                "period": period,
                "financial_health": {
                    "total_spent": total_spent, "total_income": total_income,
                    "net_balance": net_balance, "savings_rate": savings_rate,
                    "daily_burn": daily_burn, "projected_month_end_spend": projected_month_end,
                    "transactions_count": tx_count,
                },
                "structure": {
                    "subscription_total": total_subscriptions, "subscription_share": subscription_share,
                    "fixed_expense_total": total_fixed, "fixed_expense_share": fixed_share,
                    "budget_adherence": budget_adherence, "budgets_met": met_count,
                    "budgets_total": budgets_count, "top_categories": top_categories,
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
                "meta": {"generated_at": datetime.utcnow().isoformat() + "Z", "days_in_month": days_in_month, "elapsed_days": elapsed_days},
            })
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
                """SELECT category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date BETWEEN %s AND %s
                GROUP BY category_id ORDER BY total DESC""",
                (user_id, period_start, period_end),
            )
            category_rows = cur.fetchall() or []
            cur.execute(
                """SELECT COALESCE(SUM(total_amount), 0) AS total_spent
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date BETWEEN %s AND %s""",
                (user_id, period_start, period_end),
            )
            total_spent = _safe_float((cur.fetchone() or {}).get("total_spent"), 0.0)
            cur.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total_income FROM incomes WHERE user_id=%s AND income_date BETWEEN %s AND %s",
                (user_id, period_start, period_end),
            )
            total_income = _safe_float((cur.fetchone() or {}).get("total_income"), 0.0)
            if not category_rows:
                return api_response(200, {"month": period, "scenario": None, "summary": "No spending data for selected month"})
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
            return api_response(200, {
                "month": period,
                "scenario": {
                    "category": category_name, "cut_percent": round(cut_percent, 1),
                    "category_total": round(category_total, 2), "estimated_saving": estimated_saving,
                    "current_total_spent": round(total_spent, 2), "projected_total_spent": projected_spent,
                    "current_savings_rate": current_savings_rate, "projected_savings_rate": projected_savings_rate,
                },
                "available_categories": [
                    {"name": CATEGORIES.get(r.get("category_id"), "Diger"), "total": round(_safe_float(r.get("total")), 2)}
                    for r in category_rows[:8]
                ],
            })
    finally:
        release_db_connection(conn)


def handle_ai_actions(user_id, method, body, action_id=None, params=None):
    body = body or {}
    params = params or {}
    period = _parse_period((body or {}).get("month") or (params or {}).get("month"))
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if method == "GET":
                cur.execute(
                    """SELECT id, related_period, title, source_insight, priority, status, due_date, done_at, created_at, updated_at
                    FROM ai_action_items WHERE user_id=%s AND related_period=%s
                    ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'done' THEN 1 ELSE 2 END,
                             priority DESC, due_date NULLS LAST, created_at DESC""",
                    (user_id, period),
                )
                rows = cur.fetchall() or []
                done_count = len([r for r in rows if str(r.get("status")) == "done"])
                return api_response(200, {"month": period, "data": rows, "stats": {"total": len(rows), "done": done_count, "pending": len(rows) - done_count}})
            if method == "POST":
                actions = body.get("actions")
                if not isinstance(actions, list):
                    title = str(body.get("title") or "").strip()
                    if not title:
                        return api_response(400, {"error": "actions list or title is required"})
                    actions = [{"title": title, "priority": body.get("priority", "MEDIUM"), "source_insight": body.get("source_insight"), "due_in_days": body.get("due_in_days")}]
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
                        """INSERT INTO ai_action_items (user_id, related_period, title, source_insight, priority, status, due_date)
                        VALUES (%s,%s,%s,%s,%s,'pending',%s)
                        ON CONFLICT (user_id, related_period, title) DO UPDATE SET
                          priority = EXCLUDED.priority,
                          source_insight = COALESCE(NULLIF(EXCLUDED.source_insight, ''), ai_action_items.source_insight),
                          due_date = COALESCE(EXCLUDED.due_date, ai_action_items.due_date), updated_at = NOW()""",
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
                    """UPDATE ai_action_items SET status=%s, done_at=%s, updated_at=NOW()
                    WHERE id=%s AND user_id=%s
                    RETURNING id, related_period, title, source_insight, priority, status, due_date, done_at, updated_at""",
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


def handle_ai_action_apply(user_id, action_id, body):
    body = body or {}
    action_type = str(body.get("action_type") or "").strip()
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, title, status FROM ai_action_items WHERE id=%s AND user_id=%s", (action_id, user_id))
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
                    """INSERT INTO budgets (user_id, category_name, amount) VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, category_name) DO UPDATE SET amount=EXCLUDED.amount, updated_at=NOW()
                    RETURNING id, category_name, amount""",
                    (user_id, category_name[:100], amount),
                )
                result = {"type": "budget_set", "data": cur.fetchone()}
            elif action_type == "create_goal":
                title = str(body.get("title") or "").strip()
                target_amount = _safe_float(body.get("target_amount"), None)
                if not title or target_amount is None or target_amount <= 0:
                    return api_response(400, {"error": "title and valid target_amount required"})
                cur.execute(
                    """INSERT INTO financial_goals (user_id, title, target_amount, metric_type, status)
                    VALUES (%s, %s, %s, %s, 'active') RETURNING id, title, target_amount, status""",
                    (user_id, title[:120], target_amount, body.get("metric_type", "savings")),
                )
                result = {"type": "goal_created", "data": cur.fetchone()}
            elif action_type == "cancel_subscription":
                sub_name = str(body.get("subscription_name") or "").strip()
                if not sub_name:
                    return api_response(400, {"error": "subscription_name required"})
                cur.execute("DELETE FROM subscriptions WHERE user_id=%s AND LOWER(name) = LOWER(%s) RETURNING id, name", (user_id, sub_name))
                result = {"type": "subscription_cancelled", "data": cur.fetchone()}
            else:
                return api_response(400, {"error": f"Unknown action_type: {action_type}. Supported: set_budget, create_goal, cancel_subscription"})
            cur.execute("UPDATE ai_action_items SET status='done', done_at=NOW(), updated_at=NOW() WHERE id=%s AND user_id=%s", (action_id, user_id))
            conn.commit()
            return api_response(200, {"applied": True, "result": result})
    finally:
        release_db_connection(conn)


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
                """SELECT COUNT(*) AS count, COALESCE(SUM(total_amount),0) AS total, MAX(updated_at) AS last_upd
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s""",
                (user_id, period),
            )
            sig_row = cur.fetchone()
            if not sig_row or sig_row["count"] < 1:
                empty_analysis = {
                    "coach": {"headline": "Analiz için yeterli veri yok.", "summary": "Bu ay için henüz analiz edilecek harcama verisi bulunamadı.", "focus_areas": ["Fiş ekleme", "Kategori düzeni", "Bütçe takibi"]},
                    "insights": [{"id": "ins_low_data_1", "type": "data_readiness", "priority": "MEDIUM", "title": "Yapay zeka analizi için veri biriktirin", "summary": "Daha doğru tahmin ve öneriler için bu ay en az birkaç harcama kaydı ekleyin.", "confidence": 95, "actions": ["Manuel gider ekleyin", "Fiş yükleyin", "Sesli asistanla kayıt oluşturun"]}],
                    "anomalies": [], "forecast": {"next_month_estimate": 0, "trend": "stable", "confidence_score": 0}, "patterns": {},
                    "next_actions": [{"title": "Bu ay en az 3 harcamayı sisteme girin", "priority": "MEDIUM", "due_in_days": 7}],
                    "meta": {"generated_at": datetime.utcnow().isoformat() + "Z", "analysis_version": "v5", "period": period, "model_version": BEDROCK_MODEL_ID, "cache_hit": False, "insufficient_data": True},
                }
                try:
                    empty_meta = {"generated_at": datetime.utcnow().isoformat(), "data_sig": _compute_data_signature(sig_row["total"], sig_row["count"], sig_row["last_upd"] or datetime.min, persona), "model": BEDROCK_MODEL_ID, "cache_hit": False, "ttl_seconds": AI_CACHE_TTL_SECONDS}
                    cur.execute("DELETE FROM ai_insights WHERE user_id=%s AND related_period=%s", (user_id, period))
                    cur.execute("INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) VALUES (%s,%s,%s,%s)", (user_id, "__meta__", json.dumps(empty_meta, default=_json_default), period))
                    cur.execute("INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) VALUES (%s,%s,%s,%s)", (user_id, "__result__", json.dumps(empty_analysis, default=_json_default), period))
                    conn.commit()
                except Exception as e:
                    logger.error(f"Failed to save empty analysis state: {e}")
                return api_response(200, empty_analysis)
            current_data_sig = _compute_data_signature(sig_row["total"], sig_row["count"], sig_row["last_upd"] or datetime.min, persona)
            cached_meta, cached_result = None, None
            if use_cache and not force_recompute:
                cur.execute(
                    """SELECT insight_type, insight_text FROM ai_insights
                    WHERE user_id=%s AND related_period=%s AND insight_type IN ('__meta__','__result__')
                    ORDER BY created_at DESC""",
                    (user_id, period),
                )
                for row in cur.fetchall():
                    if row["insight_type"] == "__meta__" and cached_meta is None:
                        cached_meta = row["insight_text"]
                    if row["insight_type"] == "__result__" and cached_result is None:
                        cached_result = row["insight_text"]
                if isinstance(cached_meta, str):
                    try: cached_meta = json.loads(cached_meta)
                    except Exception: cached_meta = None
                if isinstance(cached_result, str):
                    try: cached_result = json.loads(cached_result)
                    except Exception: cached_result = None
                if isinstance(cached_meta, dict) and isinstance(cached_result, dict):
                    generated_at = cached_meta.get("generated_at")
                    if generated_at and cached_meta.get("data_sig") == current_data_sig:
                        try:
                            age_seconds = (datetime.utcnow() - datetime.fromisoformat(generated_at)).total_seconds()
                            if age_seconds <= AI_CACHE_TTL_SECONDS:
                                cached_result["is_stale"] = False
                                if not isinstance(cached_result.get("meta"), dict): cached_result["meta"] = {}
                                cached_result["meta"]["cache_hit"] = True
                                cached_result["meta"]["cache_age_seconds"] = int(age_seconds)
                                return api_response(200, cached_result)
                        except Exception:
                            pass
            period_start = f"{period}-01"
            cur.execute(
                """SELECT merchant_name AS merchant, total_amount AS amount, TO_CHAR(receipt_date, 'YYYY-MM-DD') AS date, category_id
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date >= DATE(%s) - INTERVAL '6 months'
                ORDER BY receipt_date ASC""",
                (user_id, period_start),
            )
            txs = cur.fetchall()
            for tx in txs:
                tx["category"] = CATEGORIES.get(tx.get("category_id"), "Diğer")
                tx["amount"] = _safe_float(tx.get("amount"))
            cur.execute(
                """SELECT TO_CHAR(DATE_TRUNC('month', receipt_date), 'YYYY-MM') AS month, category_id, SUM(total_amount) AS total
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date IS NOT NULL
                GROUP BY 1,2 ORDER BY 1""",
                (user_id,),
            )
            month_map = {}
            for row in cur.fetchall():
                month = row["month"]
                if not month: continue
                if month not in month_map:
                    month_map[month] = {"month": month, "total": 0.0, "categories": {}}
                cat_name = CATEGORIES.get(row.get("category_id"), "Diğer")
                cat_total = _safe_float(row.get("total"))
                month_map[month]["categories"][cat_name] = round(cat_total, 2)
                month_map[month]["total"] += cat_total
            monthly = []
            for month in sorted(m for m in month_map if m):
                month_map[month]["total"] = round(month_map[month]["total"], 2)
                monthly.append(month_map[month])
            cur.execute("SELECT category_name, amount FROM budgets WHERE user_id=%s", (user_id,))
            budget_rows = cur.fetchall()
            cur.execute(
                """SELECT category_id, SUM(total_amount) AS spent FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY category_id""",
                (user_id, period),
            )
            spent_map = {CATEGORIES.get(r["category_id"], "Diğer"): _safe_float(r["spent"]) for r in cur.fetchall()}
            budgets = []
            for budget in budget_rows:
                category = budget.get("category_name")
                limit_value = _safe_float(budget.get("amount"))
                spent_value = spent_map.get(category, 0.0)
                pct = round((spent_value / limit_value) * 100, 1) if limit_value > 0 else 0.0
                budgets.append({"category": category, "limit": limit_value, "spent": spent_value, "pct": pct, "budget": limit_value})
            cur.execute("SELECT name, amount FROM subscriptions WHERE user_id=%s", (user_id,))
            subscriptions = cur.fetchall()
            cur.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM incomes WHERE user_id=%s AND TO_CHAR(income_date, 'YYYY-MM')=%s",
                (user_id, period),
            )
            income_total = _safe_float((cur.fetchone() or {}).get("total"), 0.0)
            cur.execute(
                """SELECT id, title, target_amount, current_amount, target_date, metric_type, status
                FROM financial_goals WHERE user_id=%s AND status='active'
                ORDER BY target_date NULLS LAST, created_at DESC LIMIT 30""",
                (user_id,),
            )
            goals = cur.fetchall()
            spent_total = _safe_float(sig_row.get("total"), 0.0)
            savings_rate = ((income_total - spent_total) / income_total * 100) if income_total > 0 else 0.0
            payload = {
                "transactions": txs, "monthlyTotals": monthly, "budgets": budgets,
                "subscriptions": subscriptions, "goals": goals,
                "financialHealth": {"period_income": round(income_total, 2), "period_spent": round(spent_total, 2), "period_net": round(income_total - spent_total, 2), "savings_rate": round(savings_rate, 1)},
                "period": period, "categoryMap": {str(k): v for k, v in CATEGORIES.items()},
                "skipLLM": skip_llm, "persona": persona,
                # AI Lambda loglarının hangi kullanıcıya ait olduğunu bilinmesi için
                "userId": str(user_id),
            }
            logger.info(
                "Invoking AI Lambda",
                extra={
                    "user_id": user_id,
                    "method": "POST",
                    "path": "/analyze",
                    "module_name": "insights",
                    "period": period,
                    "tx_count": len(txs),
                    "skip_llm": skip_llm,
                },
            )
            invoke_resp = lambda_client.invoke(FunctionName=AI_LAMBDA_FUNCTION_NAME, InvocationType="RequestResponse", Payload=json.dumps(payload, default=_json_default))
            raw_result = json.loads(invoke_resp["Payload"].read() or "{}")
            if "body" in raw_result:
                result_body = raw_result["body"]
                if isinstance(result_body, str):
                    try: ai_result = json.loads(result_body)
                    except Exception: ai_result = {"error": "Invalid AI response body"}
                else:
                    ai_result = result_body
            else:
                ai_result = raw_result
            if not isinstance(ai_result, dict):
                return api_response(500, {"error": "AI returned invalid response"})
            meta = {
                "generated_at": datetime.utcnow().isoformat(), "data_sig": current_data_sig,
                "cache_key": ((ai_result.get("meta") or {}).get("cache_key") if isinstance(ai_result.get("meta"), dict) else None),
                "model": ((ai_result.get("meta") or {}).get("model_version") if isinstance(ai_result.get("meta"), dict) else BEDROCK_MODEL_ID),
                "cache_hit": False, "ttl_seconds": AI_CACHE_TTL_SECONDS,
            }
            cur.execute("DELETE FROM ai_insights WHERE user_id=%s AND related_period=%s", (user_id, period))
            cur.execute("INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) VALUES (%s,%s,%s,%s)", (user_id, "__meta__", json.dumps(meta, default=_json_default), period))
            cur.execute("INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period) VALUES (%s,%s,%s,%s)", (user_id, "__result__", json.dumps(ai_result, default=_json_default), period))
            for insight in ai_result.get("insights", [])[:50]:
                cur.execute(
                    "INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period, priority) VALUES (%s,%s,%s,%s,%s)",
                    (user_id, insight.get("type", "insight"), json.dumps(insight, default=_json_default), period, insight.get("priority", "MEDIUM")),
                )
            conn.commit()
            ai_result["is_stale"] = False
            if not isinstance(ai_result.get("meta"), dict): ai_result["meta"] = {}
            ai_result["meta"]["cache_hit"] = False
            ai_result["meta"]["data_sig"] = current_data_sig
            return api_response(200, ai_result)
    except Exception as exc:
        logger.error(f"AI analysis failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Analysis failed"})
    finally:
        release_db_connection(conn)
