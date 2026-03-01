from psycopg2.extras import RealDictCursor

from db import get_db_connection, release_db_connection
from helpers import _safe_float, api_response


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
                    """INSERT INTO subscriptions (user_id, name, amount, next_payment_date)
                    VALUES (%s,%s,%s,%s) RETURNING id""",
                    (user_id, name, amount, next_payment_date),
                )
                created = cur.fetchone()
                conn.commit()
                return api_response(201, {"message": "Subscription added", "id": created["id"]})
            if method in {"PUT", "PATCH"} and sub_id:
                body = body or {}
                cur.execute("SELECT id FROM subscriptions WHERE id=%s AND user_id=%s", (sub_id, user_id))
                if not cur.fetchone():
                    return api_response(404, {"error": "Subscription not found"})
                name = str(body.get("name") or "").strip()
                amount = _safe_float(body.get("amount"), None)
                next_payment_date = body.get("next_payment_date")
                if not name or amount is None or amount <= 0:
                    return api_response(400, {"error": "name and valid amount are required"})
                cur.execute(
                    """UPDATE subscriptions SET name=%s, amount=%s, next_payment_date=%s
                    WHERE id=%s AND user_id=%s
                    RETURNING id, name, amount, next_payment_date, created_at""",
                    (name, amount, next_payment_date, sub_id, user_id),
                )
                conn.commit()
                return api_response(200, cur.fetchone())
            if method == "DELETE" and sub_id:
                cur.execute("DELETE FROM subscriptions WHERE id=%s AND user_id=%s", (sub_id, user_id))
                conn.commit()
                return api_response(200, {"message": "Deleted"})
            return api_response(400, {"error": "Invalid request"})
    finally:
        release_db_connection(conn)
