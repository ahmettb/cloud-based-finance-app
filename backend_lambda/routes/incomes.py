from datetime import date

from psycopg2.extras import RealDictCursor

from db import get_db_connection, release_db_connection
from helpers import _safe_float, api_response


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
                    """INSERT INTO incomes (user_id, source, amount, income_date, description)
                    VALUES (%s,%s,%s,%s,%s)
                    RETURNING id, source, amount, income_date, description, created_at""",
                    (user_id, source, amount, income_date, description),
                )
                conn.commit()
                return api_response(201, cur.fetchone())
            if method in {"PUT", "PATCH"} and income_id:
                body = body or {}
                cur.execute("SELECT id FROM incomes WHERE id=%s AND user_id=%s", (income_id, user_id))
                if not cur.fetchone():
                    return api_response(404, {"error": "Income not found"})
                source = str(body.get("source") or "").strip()
                amount = _safe_float(body.get("amount"), None)
                income_date = body.get("income_date")
                description = str(body.get("description") or "").strip()
                if not source or amount is None or amount <= 0:
                    return api_response(400, {"error": "source and valid amount are required"})
                cur.execute(
                    """UPDATE incomes SET source=%s, amount=%s, income_date=%s, description=%s
                    WHERE id=%s AND user_id=%s
                    RETURNING id, source, amount, income_date, description, created_at""",
                    (source, amount, income_date, description, income_id, user_id),
                )
                conn.commit()
                return api_response(200, cur.fetchone())
            if method == "DELETE" and income_id:
                cur.execute("DELETE FROM incomes WHERE id=%s AND user_id=%s", (income_id, user_id))
                conn.commit()
                return api_response(200, {"message": "Deleted"})
            return api_response(400, {"error": "Invalid request"})
    finally:
        release_db_connection(conn)
