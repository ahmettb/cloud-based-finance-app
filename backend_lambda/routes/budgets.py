from datetime import datetime

from psycopg2.extras import RealDictCursor

from config import CATEGORIES, logger
from db import get_db_connection, release_db_connection
from helpers import _safe_float, api_response


def handle_get_budgets(user_id):
    period = datetime.now().strftime("%Y-%m")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, user_id, category_name, amount, updated_at FROM budgets WHERE user_id=%s", (user_id,))
            budgets = cur.fetchall()
            cur.execute(
                """SELECT category_id, SUM(total_amount) AS spent
                FROM receipts
                WHERE user_id=%s AND status != 'deleted' AND TO_CHAR(receipt_date, 'YYYY-MM')=%s
                GROUP BY category_id""",
                (user_id, period)
            )
            receipt_spent_rows = cur.fetchall()
            cur.execute(
                """SELECT g.category_type, SUM(p.amount) AS spent
                FROM fixed_expense_payments p
                JOIN fixed_expense_items i ON i.id = p.item_id
                JOIN fixed_expense_groups g ON g.id = i.group_id
                WHERE p.user_id=%s AND p.status = 'paid' AND TO_CHAR(p.payment_date, 'YYYY-MM')=%s
                GROUP BY g.category_type""",
                (user_id, period)
            )
            fixed_spent_rows = cur.fetchall()
            receipt_spent_by_name = {}
            for r in receipt_spent_rows:
                cat_id = r.get("category_id")
                if cat_id is not None:
                    try:
                        cat_id = int(cat_id)
                    except ValueError:
                        pass
                c_name = CATEGORIES.get(cat_id, "Diğer")
                receipt_spent_by_name[c_name] = receipt_spent_by_name.get(c_name, 0.0) + _safe_float(r.get("spent"), 0.0)
            fixed_spent_by_name = {}
            for r in fixed_spent_rows:
                c_name = r.get("category_type") or "Diğer"
                fixed_spent_by_name[c_name] = fixed_spent_by_name.get(c_name, 0.0) + _safe_float(r.get("spent"), 0.0)
            normalized = []
            for b in budgets:
                c_name = b["category_name"]
                limit_value = _safe_float(b.get("amount"), 0.0)
                spent = receipt_spent_by_name.get(c_name, 0.0) + fixed_spent_by_name.get(c_name, 0.0)
                pct = round((spent / limit_value) * 100, 1) if limit_value > 0 else 0.0
                b["spent"] = spent
                b["percentage"] = pct
                normalized.append(b)
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
                """INSERT INTO budgets (user_id, category_name, amount)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, category_name)
                DO UPDATE SET amount=EXCLUDED.amount, updated_at=NOW()""",
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
            cur.execute("DELETE FROM budgets WHERE id=%s AND user_id=%s", (budget_id, user_id))
            if cur.rowcount == 0:
                return api_response(404, {"error": "Budget not found"})
            conn.commit()
            return api_response(200, {"message": "Budget deleted"})
    finally:
        release_db_connection(conn)
