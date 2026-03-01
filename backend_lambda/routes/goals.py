from psycopg2.extras import RealDictCursor

from db import get_db_connection, release_db_connection
from helpers import _safe_float, api_response


def _normalize_goal_status(value, default="active"):
    allowed = {"active", "completed", "archived"}
    candidate = str(value or default).strip().lower()
    return candidate if candidate in allowed else default


def _normalize_goal_type(value, default="savings"):
    allowed = {"savings", "expense_reduction", "income_growth"}
    candidate = str(value or default).strip().lower()
    return candidate if candidate in allowed else default


def handle_goals(user_id, method, body, goal_id=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if method == "GET":
                cur.execute(
                    """SELECT id, title, target_amount, current_amount, target_date,
                           metric_type, status, notes, created_at, updated_at,
                           CASE WHEN target_amount > 0 THEN ROUND((current_amount / target_amount) * 100, 1) ELSE 0 END AS progress_pct,
                           GREATEST(target_amount - current_amount, 0) AS remaining_amount
                    FROM financial_goals
                    WHERE user_id = %s AND status != 'archived'
                    ORDER BY CASE WHEN status = 'completed' THEN 1 ELSE 0 END ASC,
                             target_date NULLS LAST, created_at DESC""",
                    (user_id,),
                )
                return api_response(200, {"data": cur.fetchall()})
            if method == "POST":
                body = body or {}
                title = str(body.get("title") or "").strip()
                target_amount = _safe_float(body.get("target_amount"), None)
                current_amount = _safe_float(body.get("current_amount"), 0.0)
                target_date = body.get("target_date")
                metric_type = _normalize_goal_type(body.get("metric_type"))
                status = _normalize_goal_status(body.get("status"), "active")
                notes = str(body.get("notes") or "").strip()[:280]
                if not title or target_amount is None or target_amount <= 0:
                    return api_response(400, {"error": "title and positive target_amount are required"})
                if current_amount < 0:
                    return api_response(400, {"error": "current_amount cannot be negative"})
                cur.execute(
                    """INSERT INTO financial_goals (user_id, title, target_amount, current_amount, target_date, metric_type, status, notes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id, title, target_amount, current_amount, target_date, metric_type, status, notes, created_at, updated_at""",
                    (user_id, title, target_amount, current_amount, target_date, metric_type, status, notes),
                )
                conn.commit()
                return api_response(201, cur.fetchone())
            if method == "PUT" and goal_id:
                body = body or {}
                cur.execute("SELECT id FROM financial_goals WHERE id=%s AND user_id=%s", (goal_id, user_id))
                if not cur.fetchone():
                    return api_response(404, {"error": "Goal not found"})
                fields, values = [], []
                if body.get("title") is not None:
                    title = str(body["title"]).strip()
                    if not title:
                        return api_response(400, {"error": "title cannot be empty"})
                    fields.append("title=%s"); values.append(title)
                if body.get("target_amount") is not None:
                    ta = _safe_float(body["target_amount"], None)
                    if ta is None or ta <= 0:
                        return api_response(400, {"error": "target_amount must be positive"})
                    fields.append("target_amount=%s"); values.append(ta)
                if body.get("current_amount") is not None:
                    ca = _safe_float(body["current_amount"], None)
                    if ca is None or ca < 0:
                        return api_response(400, {"error": "current_amount cannot be negative"})
                    fields.append("current_amount=%s"); values.append(ca)
                if body.get("target_date") is not None:
                    fields.append("target_date=%s"); values.append(body["target_date"] or None)
                if body.get("metric_type") is not None:
                    fields.append("metric_type=%s"); values.append(_normalize_goal_type(body["metric_type"]))
                if body.get("status") is not None:
                    fields.append("status=%s"); values.append(_normalize_goal_status(body["status"]))
                if body.get("notes") is not None:
                    fields.append("notes=%s"); values.append(str(body["notes"]).strip()[:280])
                if not fields:
                    return api_response(400, {"error": "No updatable fields provided"})
                fields.append("updated_at=NOW()")
                values.extend([goal_id, user_id])
                cur.execute(
                    f"""UPDATE financial_goals SET {', '.join(fields)}
                    WHERE id=%s AND user_id=%s
                    RETURNING id, title, target_amount, current_amount, target_date, metric_type, status, notes, created_at, updated_at""",
                    tuple(values),
                )
                conn.commit()
                return api_response(200, cur.fetchone())
            if method == "DELETE" and goal_id:
                cur.execute("UPDATE financial_goals SET status='archived', updated_at=NOW() WHERE id=%s AND user_id=%s", (goal_id, user_id))
                conn.commit()
                return api_response(200, {"message": "Goal archived"})
            return api_response(400, {"error": "Invalid request"})
    finally:
        release_db_connection(conn)
