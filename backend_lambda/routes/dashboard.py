import hashlib
import json
from datetime import datetime

from psycopg2.extras import RealDictCursor

from config import CATEGORIES, logger
from db import get_db_connection, release_db_connection
from helpers import _json_default, _safe_float, api_response


def _compute_data_signature(total_amount, receipt_count, last_upd, persona="friendly"):
    raw = f"{_safe_float(total_amount)}-{int(receipt_count)}-{last_upd}-{persona}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def handle_dashboard(user_id):
    period = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT COUNT(*) AS count, COALESCE(SUM(total_amount),0) AS total,
                       COALESCE(AVG(total_amount),0) AS avg_amount, MAX(updated_at) AS last_upd
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s""",
                (user_id, period),
            )
            summary_row = cur.fetchone()
            cur.execute("SELECT COUNT(*) AS total_count FROM receipts WHERE user_id=%s", (user_id,))
            total_receipt_count = int(cur.fetchone()["total_count"])
            cur.execute(
                """SELECT category_id, COALESCE(SUM(total_amount),0) AS total
                FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY category_id""",
                (user_id, period),
            )
            category_rows = cur.fetchall()
            cur.execute(
                """SELECT COUNT(*) as fp_count, COALESCE(SUM(p.amount),0) as fp_total
                FROM fixed_expense_payments p
                WHERE p.user_id=%s AND p.status='paid' AND TO_CHAR(p.payment_date, 'YYYY-MM')=%s""",
                (user_id, period),
            )
            fp_summary = cur.fetchone()
            cur.execute(
                """SELECT g.category_type, COALESCE(SUM(p.amount),0) AS total
                FROM fixed_expense_payments p
                JOIN fixed_expense_items i ON i.id = p.item_id
                JOIN fixed_expense_groups g ON g.id = i.group_id
                WHERE p.user_id=%s AND p.status='paid' AND TO_CHAR(p.payment_date, 'YYYY-MM')=%s
                GROUP BY g.category_type""",
                (user_id, period),
            )
            fp_categories = cur.fetchall()
            categories = {}
            for row in category_rows:
                categories[CATEGORIES.get(row.get("category_id"), "Diğer")] = round(_safe_float(row.get("total")), 2)
            for row in fp_categories:
                cat_name = row.get("category_type") or "Diğer"
                categories[cat_name] = categories.get(cat_name, 0.0) + round(_safe_float(row.get("total")), 2)
            cur.execute(
                """SELECT insight_type, insight_text FROM ai_insights
                WHERE user_id=%s AND related_period=%s AND insight_type IN ('__meta__','__result__')
                ORDER BY created_at DESC""",
                (user_id, period),
            )
            meta, saved_analysis = None, None
            for row in cur.fetchall():
                if row["insight_type"] == "__meta__" and meta is None: meta = row["insight_text"]
                if row["insight_type"] == "__result__" and saved_analysis is None: saved_analysis = row["insight_text"]
            if isinstance(meta, str):
                try: meta = json.loads(meta)
                except Exception: meta = None
            if isinstance(saved_analysis, str):
                try: saved_analysis = json.loads(saved_analysis)
                except Exception: saved_analysis = None
            data_sig = _compute_data_signature(
                _safe_float(summary_row["total"]) + _safe_float(fp_summary["fp_total"]),
                int(summary_row["count"]) + int(fp_summary["fp_count"]),
                summary_row["last_upd"] or datetime.min,
            )
            is_stale = True
            if meta and isinstance(meta, dict):
                generated_at = meta.get("generated_at")
                if generated_at and meta.get("data_sig") == data_sig:
                    try:
                        age = (datetime.utcnow() - datetime.fromisoformat(generated_at)).total_seconds()
                        if age <= 6 * 3600: is_stale = False
                    except Exception:
                        is_stale = meta.get("data_sig") != data_sig
            if isinstance(saved_analysis, dict):
                saved_analysis["is_stale"] = is_stale
            total_spent = round(_safe_float(summary_row["total"]) + _safe_float(fp_summary["fp_total"]), 2)
            count = int(summary_row["count"]) + int(fp_summary["fp_count"])
            avg_amount = round(total_spent / count, 2) if count > 0 else 0.0
            cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM incomes WHERE user_id=%s AND TO_CHAR(income_date, 'YYYY-MM')=%s", (user_id, period))
            total_income = round(_safe_float(cur.fetchone()["total"]), 2)
            net_balance = round(total_income - total_spent, 2)
            cur.execute("SELECT id, category_name, amount FROM budgets WHERE user_id=%s LIMIT 3", (user_id,))
            budget_rows_dash = cur.fetchall()
            cur.execute("SELECT category_id, SUM(total_amount) AS spent FROM receipts WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s GROUP BY category_id", (user_id, period))
            spent_dash_map = {}
            for r in cur.fetchall():
                spent_dash_map[CATEGORIES.get(r["category_id"], "Diğer")] = _safe_float(r["spent"])
            for row in fp_categories:
                cat_name = row.get("category_type") or "Diğer"
                spent_dash_map[cat_name] = spent_dash_map.get(cat_name, 0.0) + _safe_float(row.get("total"))
            budgets = []
            for b in budget_rows_dash:
                cat = b.get("category_name")
                lim = _safe_float(b.get("amount"), 0.0)
                sp = spent_dash_map.get(cat, 0.0)
                pct = round((sp / lim) * 100, 1) if lim > 0 else 0.0
                budgets.append({"id": str(b.get("id", "")), "category_name": cat, "amount": lim, "spent": sp, "percentage": pct})
            cur.execute("SELECT name, amount, next_payment_date FROM subscriptions WHERE user_id=%s", (user_id,))
            subscriptions = cur.fetchall()
            
            # Giderlerden (Receipts) "Abonelik" (Kategori 9) olanları getir
            cur.execute("""
                SELECT merchant_name AS name, total_amount AS amount, receipt_date AS next_payment_date 
                FROM receipts 
                WHERE user_id=%s AND category_id=9 AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
            """, (user_id, period))
            for r in cur.fetchall():
                subscriptions.append({
                    "name": r.get("name") or "Abonelik (Fiş/Fatura)",
                    "amount": _safe_float(r.get("amount")),
                    "next_payment_date": r.get("next_payment_date")
                })
                
            # Sabit Giderlerden "Abonelik" kategorisindekileri getir
            cur.execute("""
                SELECT i.title AS name, p.amount, p.payment_date AS next_payment_date
                FROM fixed_expense_payments p
                JOIN fixed_expense_items i ON p.item_id = i.id
                JOIN fixed_expense_groups g ON i.group_id = g.id
                WHERE p.user_id=%s AND p.status='paid' AND g.category_type='Abonelik' AND TO_CHAR(p.payment_date, 'YYYY-MM')=%s
            """, (user_id, period))
            for r in cur.fetchall():
                subscriptions.append({
                    "name": r.get("name") or "Sabit Abonelik",
                    "amount": _safe_float(r.get("amount")),
                    "next_payment_date": r.get("next_payment_date")
                })

            # Aynı isimdeki aboneliklerin tutarlarını topla ve tekrarı önle
            seen_subs = {}
            for sub in subscriptions:
                n = sub["name"]
                if n not in seen_subs:
                    seen_subs[n] = {"name": n, "amount": _safe_float(sub.get("amount")), "next_payment_date": sub.get("next_payment_date")}
                else:
                    seen_subs[n]["amount"] += _safe_float(sub.get("amount"))

            # En yüksek tutara sahip 5 aboneliği göster
            final_subs = sorted(list(seen_subs.values()), key=lambda x: x["amount"], reverse=True)[:5]
            cur.execute(
                """SELECT COUNT(*) FILTER (WHERE status='active') AS active_count,
                       COUNT(*) FILTER (WHERE status='completed') AS completed_count,
                       COALESCE(SUM(target_amount) FILTER (WHERE status='active'), 0) AS active_target_total,
                       COALESCE(SUM(current_amount) FILTER (WHERE status='active'), 0) AS active_current_total
                FROM financial_goals WHERE user_id=%s""",
                (user_id,),
            )
            goals = cur.fetchone() or {}
            active_target = _safe_float(goals.get("active_target_total"), 0.0)
            active_current = _safe_float(goals.get("active_current_total"), 0.0)
            goal_pct = round((active_current / active_target) * 100, 1) if active_target > 0 else 0.0
            return api_response(200, {
                "period": period, "total_spent": total_spent, "total_income": total_income,
                "net_balance": net_balance, "avg_amount": avg_amount,
                "total_receipt_count": total_receipt_count, "categories": categories,
                "budgets": budgets, "subscriptions": final_subs,
                "goals_summary": {
                    "active_count": int(goals.get("active_count") or 0),
                    "completed_count": int(goals.get("completed_count") or 0),
                    "active_target_total": round(active_target, 2),
                    "active_current_total": round(active_current, 2),
                    "active_progress_pct": goal_pct,
                },
                "currency": "TRY", "is_stale": is_stale, "saved_analysis": saved_analysis,
                "summary": {"total": total_spent, "count": count, "currency": "TRY"},
            })
    finally:
        release_db_connection(conn)
