import json
import re
from datetime import datetime, timedelta

from psycopg2.extras import RealDictCursor

from config import CATEGORIES, logger
from db import get_db_connection, release_db_connection
from helpers import _json_default, _parse_period, _safe_float, api_response


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
                """SELECT TO_CHAR(DATE_TRUNC('month', receipt_date), 'YYYY-MM') AS month,
                       COUNT(*) AS receipt_count, COALESCE(SUM(total_amount),0) AS total_expense,
                       COALESCE(AVG(total_amount),0) AS avg_expense
                FROM receipts WHERE user_id=%s AND status='completed' AND receipt_date >= %s
                GROUP BY 1 ORDER BY 1 DESC""",
                (user_id, period_start),
            )
            monthly_rows = cur.fetchall()
            cur.execute(
                """SELECT TO_CHAR(DATE_TRUNC('month', receipt_date), 'YYYY-MM') AS month,
                       category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts WHERE user_id=%s AND status='completed' AND receipt_date >= %s
                GROUP BY 1,2 ORDER BY 1 DESC, total DESC""",
                (user_id, period_start),
            )
            category_rows = cur.fetchall()
            cur.execute(
                """SELECT COALESCE(SUM(total_amount),0) AS total_expense, COUNT(*) AS total_receipts,
                       COALESCE(AVG(total_amount),0) AS avg_receipt_amount
                FROM receipts WHERE user_id=%s AND status='completed' AND receipt_date >= %s""",
                (user_id, period_start),
            )
            totals = cur.fetchone()
            cur.execute(
                """SELECT category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts WHERE user_id=%s AND status='completed' AND receipt_date >= %s
                GROUP BY category_id ORDER BY total DESC LIMIT 5""",
                (user_id, period_start),
            )
            top_categories = cur.fetchall()
        category_by_month = {}
        for row in category_rows:
            mk = row["month"]
            if mk not in category_by_month:
                category_by_month[mk] = []
            category_by_month[mk].append({"category_id": row["category_id"], "category_name": CATEGORIES.get(row["category_id"], "Diğer"), "total": round(_safe_float(row["total"]), 2)})
        data = []
        for row in monthly_rows:
            mk = row["month"]
            mc = category_by_month.get(mk, [])
            data.append({"month": mk, "total_expense": round(_safe_float(row["total_expense"]), 2), "avg_expense": round(_safe_float(row["avg_expense"]), 2), "receipt_count": int(row["receipt_count"] or 0), "top_category": mc[0] if mc else None, "categories": mc})
        return api_response(200, {
            "period_start": period_start.isoformat(), "period_end": today.isoformat(), "months": months, "currency": "TRY",
            "summary": {"total_expense": round(_safe_float(totals["total_expense"]), 2), "total_receipts": int(totals["total_receipts"] or 0), "avg_receipt_amount": round(_safe_float(totals["avg_receipt_amount"]), 2),
                "top_categories": [{"category_id": r["category_id"], "category_name": CATEGORIES.get(r["category_id"], "Diğer"), "total": round(_safe_float(r["total"]), 2)} for r in top_categories]},
            "data": data,
        })
    finally:
        release_db_connection(conn)


def handle_chart_data(user_id, params):
    params = params or {}
    rng = params.get("range", "1m")
    group_type = params.get("type", "total")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            interval_map = {"1w": "7 days", "1m": "1 month", "3m": "3 months", "6m": "6 months", "1y": "1 year"}
            db_interval = interval_map.get(rng, "1 month")
            is_daily = rng in ["1w", "1m"]
            date_format = "YYYY-MM-DD" if is_daily else "YYYY-MM"
            if group_type == "category":
                cur.execute(
                    f"""WITH receipt_data AS (
                        SELECT TO_CHAR(receipt_date, %s) as date_label, category_id, SUM(total_amount) as total
                        FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date >= DATE(NOW()) - INTERVAL %s GROUP BY 1, 2
                    ), fixed_data AS (
                        SELECT TO_CHAR(p.payment_date, %s) as date_label, g.category_type, SUM(p.amount) as total
                        FROM fixed_expense_payments p JOIN fixed_expense_items i ON i.id = p.item_id JOIN fixed_expense_groups g ON g.id = i.group_id
                        WHERE p.user_id=%s AND p.status = 'paid' AND p.payment_date >= DATE(NOW()) - INTERVAL %s GROUP BY 1, 2
                    )
                    SELECT date_label, category_id, NULL as category_type, total, 'receipt' as source FROM receipt_data
                    UNION ALL SELECT date_label, NULL as category_id, category_type, total, 'fixed' as source FROM fixed_data
                    ORDER BY date_label ASC""",
                    (date_format, user_id, db_interval, date_format, user_id, db_interval)
                )
                consolidated = {}
                for row in cur.fetchall():
                    cat_name = CATEGORIES.get(row.get("category_id"), row.get("category_type") or "Diğer")
                    c_key = (row["date_label"], cat_name)
                    if c_key not in consolidated:
                        consolidated[c_key] = {"date_label": row["date_label"], "category_name": cat_name, "total": 0.0}
                    consolidated[c_key]["total"] += _safe_float(row["total"])
                return api_response(200, {"data": list(consolidated.values()), "range": rng, "type": "category", "is_daily": is_daily})
            else:
                cur.execute(
                    f"""WITH trend_data AS (
                        SELECT TO_CHAR(receipt_date, %s) as date_label, SUM(total_amount) as total
                        FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date >= DATE(NOW()) - INTERVAL %s GROUP BY 1
                        UNION ALL
                        SELECT TO_CHAR(payment_date, %s) as date_label, SUM(amount) as total
                        FROM fixed_expense_payments WHERE user_id=%s AND status = 'paid' AND payment_date >= DATE(NOW()) - INTERVAL %s GROUP BY 1
                    ) SELECT date_label, SUM(total) as total FROM trend_data GROUP BY 1 ORDER BY 1 ASC""",
                    (date_format, user_id, db_interval, date_format, user_id, db_interval)
                )
                return api_response(200, {"data": cur.fetchall(), "range": rng, "type": "total", "is_daily": is_daily})
    finally:
        release_db_connection(conn)


def handle_reports_detailed(user_id, params):
    params = params or {}
    month_str = params.get("month", datetime.now().strftime("%Y-%m"))
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total, COALESCE(AVG(total_amount), 0) as avg FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s", (user_id, month_str))
            stats = cur.fetchone()
            cur.execute("SELECT merchant_name, total_amount, receipt_date, category_id FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s ORDER BY total_amount DESC LIMIT 1", (user_id, month_str))
            highest = cur.fetchone()
            if highest:
                highest["category_name"] = CATEGORIES.get(highest["category_id"], "Diğer")
            cur.execute(
                """SELECT CASE WHEN EXTRACT(DOW FROM receipt_date) IN (0, 6) THEN 'Hafta Sonu' ELSE 'Hafta İçi' END as day_type,
                       COUNT(*) as count, SUM(total_amount) as total
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s GROUP BY 1""",
                (user_id, month_str)
            )
            day_analysis = cur.fetchall()
            cur.execute(
                "SELECT category_id, SUM(total_amount) as total, COUNT(*) as count FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s GROUP BY 1 ORDER BY total DESC",
                (user_id, month_str)
            )
            categories_data = [{"name": CATEGORIES.get(r["category_id"], "Diğer"), "value": float(r["total"]), "count": int(r["count"])} for r in cur.fetchall()]
            cur.execute(
                """SELECT TO_CHAR(receipt_date, 'YYYY-MM') as month, SUM(total_amount) as total
                FROM receipts WHERE user_id=%s AND status != 'deleted'
                  AND receipt_date >= (TO_DATE(%s, 'YYYY-MM') - INTERVAL '5 months')
                  AND receipt_date < (TO_DATE(%s, 'YYYY-MM') + INTERVAL '1 month')
                GROUP BY 1 ORDER BY 1 ASC""",
                (user_id, month_str, month_str)
            )
            trend = cur.fetchall()
            return api_response(200, {
                "period": month_str,
                "stats": {"total": float(stats["total"]), "count": int(stats["count"]), "avg": float(stats["avg"])},
                "highest_expense": highest, "day_analysis": day_analysis,
                "category_breakdown": categories_data, "trend": trend,
            })
    finally:
        release_db_connection(conn)


def handle_reports_ai_summary(user_id, params):
    params = params or {}
    month_str = params.get("month", datetime.now().strftime("%Y-%m"))
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS count, COALESCE(SUM(total_amount), 0) AS total, COALESCE(AVG(total_amount), 0) AS avg FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s", (user_id, month_str))
            stats = cur.fetchone() or {"count": 0, "total": 0, "avg": 0}
            count = int(stats.get("count") or 0)
            total = _safe_float(stats.get("total"), 0.0)
            avg = _safe_float(stats.get("avg"), 0.0)
            cur.execute("SELECT category_id, SUM(total_amount) AS total, COUNT(*) AS count FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s GROUP BY category_id ORDER BY total DESC LIMIT 3", (user_id, month_str))
            category_rows = cur.fetchall()
            cur.execute("SELECT COALESCE(merchant_name, 'Bilinmeyen') AS merchant, COUNT(*) AS tx_count, SUM(total_amount) AS total, AVG(total_amount) AS avg_amount FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s GROUP BY 1 ORDER BY tx_count DESC, total DESC LIMIT 5", (user_id, month_str))
            merchant_rows = cur.fetchall()
            cur.execute("SELECT id, merchant_name, total_amount, receipt_date, category_id FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s ORDER BY total_amount DESC LIMIT 2", (user_id, month_str))
            highest_rows = cur.fetchall()
            cur.execute("SELECT CASE WHEN EXTRACT(DOW FROM receipt_date) IN (0,6) THEN 'weekend' ELSE 'weekday' END AS day_type, COUNT(*) AS count, COALESCE(SUM(total_amount), 0) AS total FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s GROUP BY 1", (user_id, month_str))
            day_rows = cur.fetchall()
            cur.execute("SELECT TO_CHAR(receipt_date, 'YYYY-MM') AS month, COALESCE(SUM(total_amount), 0) AS total FROM receipts WHERE user_id=%s AND status != 'deleted' AND receipt_date >= (TO_DATE(%s, 'YYYY-MM') - INTERVAL '1 month') AND receipt_date < (TO_DATE(%s, 'YYYY-MM') + INTERVAL '1 month') GROUP BY 1 ORDER BY 1 ASC", (user_id, month_str, month_str))
            month_compare_rows = cur.fetchall()
            weekend_total, weekday_total = 0.0, 0.0
            for r in day_rows:
                if r.get("day_type") == "weekend": weekend_total = _safe_float(r.get("total"), 0.0)
                else: weekday_total = _safe_float(r.get("total"), 0.0)
            risk_score = 20
            if avg > 0 and total > (avg * count * 1.05): risk_score += 10
            if weekend_total > weekday_total and weekend_total > 0: risk_score += 20
            if count > 0 and highest_rows:
                top_amt = _safe_float(highest_rows[0].get("total_amount"), 0.0)
                if avg > 0 and top_amt >= avg * 2.2: risk_score += 25
            if count >= 20: risk_score += 10
            risk_score = int(max(0, min(100, risk_score)))
            current_month_total, prev_month_total = total, 0.0
            for row in month_compare_rows:
                m = row.get("month")
                if m == month_str: current_month_total = _safe_float(row.get("total"), current_month_total)
                else: prev_month_total = _safe_float(row.get("total"), prev_month_total)
            trend_pct = ((current_month_total - prev_month_total) / prev_month_total) * 100 if prev_month_total > 0 else 0.0
            top_category = category_rows[0] if category_rows else None
            top_cat_name = CATEGORIES.get((top_category or {}).get("category_id"), "Diğer") if top_category else "Belirsiz"
            monthly_summary = f"{month_str} döneminde toplam {total:.0f} TL harcama ve {count} işlem kaydı var. En baskın kategori: {top_cat_name}."
            if prev_month_total > 0:
                monthly_summary += f" Bir önceki aya göre %{abs(trend_pct):.1f} {'artış' if trend_pct > 0 else 'düşüş'} gözleniyor."
            critical_events = [{"id": f"high_{i}", "type": "high_spend", "title": f"Yüksek harcama: {_safe_float(r.get('total_amount'),0):.0f} TL", "merchant": r.get("merchant_name") or "Bilinmeyen", "amount": _safe_float(r.get("total_amount"),0), "date": r.get("receipt_date"), "category": CATEGORIES.get(r.get("category_id"), "Diğer"), "reason": "Aylık en yüksek tutarlı işlemler arasında.", "confidence": 90} for i, r in enumerate(highest_rows, 1)]
            merchant_frequency = [{"merchant": r.get("merchant") or "Bilinmeyen", "tx_count": int(r.get("tx_count") or 0), "total": _safe_float(r.get("total"),0), "avg_amount": _safe_float(r.get("avg_amount"),0)} for r in merchant_rows]
            category_comments = []
            for row in category_rows[:3]:
                ct = _safe_float(row.get("total"), 0.0)
                pct = (ct / total * 100) if total > 0 else 0
                category_comments.append({"category": CATEGORIES.get(row.get("category_id"), "Diğer"), "comment": f"Bu kategoride {int(row.get('count') or 0)} işlem ile toplam {ct:.0f} TL (%{pct:.1f}) harcandı.", "confidence": 88})
            what_if = []
            if top_category:
                tc_total = _safe_float(top_category.get("total"), 0.0)
                for ratio in (0.1, 0.15):
                    what_if.append({"title": f"{top_cat_name} kategorisinde %{int(ratio*100)} azaltım", "estimated_monthly_saving": round(tc_total * ratio, 2), "reason": "En büyük kategori payı buradan geliyor.", "confidence": 80})
            return api_response(200, {
                "month": month_str, "risk_score": risk_score, "monthly_summary": monthly_summary,
                "critical_events": critical_events, "merchant_frequency": merchant_frequency,
                "what_if": what_if, "category_comments": category_comments,
                "meta": {"generated_at": datetime.utcnow().isoformat() + "Z", "confidence": 82 if count >= 8 else 65, "input_stats": {"transaction_count": count, "total_spent": round(total, 2), "weekend_total": round(weekend_total, 2), "weekday_total": round(weekday_total, 2)}},
            })
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
    payload = {"month": month, "feedback_type": feedback_type, "section": section, "item_id": item_id, "note": note, "source": "reports", "created_at": datetime.utcnow().isoformat() + "Z"}
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO ai_insights (user_id, insight_type, insight_text, related_period, priority) VALUES (%s,%s,%s,%s,%s)", (user_id, "__feedback__", json.dumps(payload, default=_json_default), month, "LOW"))
            conn.commit()
        return api_response(200, {"message": "Feedback kaydedildi"})
    finally:
        release_db_connection(conn)
