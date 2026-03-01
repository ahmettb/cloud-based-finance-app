import re
from datetime import date, datetime

from psycopg2.extras import RealDictCursor

from db import get_db_connection, release_db_connection
from helpers import _coerce_bool, _period_bounds, _resolve_due_date_for_period, _safe_float, api_response


def _fixed_expense_status(month_payment, due_date, period):
    if month_payment:
        status = str(month_payment.get("status") or "").strip().lower()
        if status in {"paid", "pending"}:
            return status
    if due_date < date.today() and period == datetime.now().strftime("%Y-%m"):
        return "overdue"
    return "pending"


def handle_fixed_expenses_get(user_id, params):
    params = params or {}
    period, period_start, period_end = _period_bounds(params.get("month"))
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT g.id AS group_id, g.title, g.category_type, g.created_at AS group_created_at,
                       i.id AS item_id, i.name AS item_name, i.amount AS item_amount,
                       i.due_day, i.created_at AS item_created_at
                FROM fixed_expense_groups g
                LEFT JOIN fixed_expense_items i ON i.group_id = g.id AND i.is_active = TRUE
                WHERE g.user_id = %s AND g.is_active = TRUE
                ORDER BY g.created_at DESC, i.due_day ASC, i.created_at ASC""",
                (user_id,),
            )
            rows = cur.fetchall()
            if not rows:
                return api_response(200, {
                    "month": period,
                    "stats": {"total": 0, "paid": 0, "remaining": 0, "count": 0, "pending_count": 0},
                    "data": [],
                })
            item_ids = [str(r["item_id"]) for r in rows if r.get("item_id")]
            month_payments = {}
            if item_ids:
                cur.execute(
                    """SELECT id, item_id, payment_date, amount, status, note, source, created_at, updated_at
                    FROM fixed_expense_payments
                    WHERE user_id=%s AND item_id = ANY(%s::uuid[]) AND payment_date >= %s AND payment_date <= %s
                    ORDER BY payment_date DESC, created_at DESC""",
                    (user_id, item_ids, period_start, period_end),
                )
                for pay in cur.fetchall():
                    key = str(pay["item_id"])
                    if key not in month_payments:
                        month_payments[key] = pay
            history_map = {}
            if item_ids:
                cur.execute(
                    """SELECT id, item_id, payment_date, amount, status
                    FROM (
                        SELECT id, item_id, payment_date, amount, status, created_at,
                               ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY payment_date DESC, created_at DESC) AS rn
                        FROM fixed_expense_payments WHERE user_id=%s AND item_id = ANY(%s::uuid[])
                    ) ranked WHERE rn <= 6 ORDER BY item_id, payment_date DESC""",
                    (user_id, item_ids),
                )
                for row in cur.fetchall():
                    key = str(row["item_id"])
                    history_map.setdefault(key, []).append({
                        "id": row["id"], "date": row["payment_date"],
                        "amount": _safe_float(row["amount"]), "status": row["status"],
                    })
            group_map = {}
            for row in rows:
                gid = str(row["group_id"])
                if gid not in group_map:
                    group_map[gid] = {
                        "id": row["group_id"], "title": row["title"],
                        "category_type": row["category_type"] or "Diger", "items": [],
                    }
                if not row.get("item_id"):
                    continue
                item_id = str(row["item_id"])
                due_day = int(row.get("due_day") or 1)
                due_date = _resolve_due_date_for_period(period, due_day)
                month_payment = month_payments.get(item_id)
                status = _fixed_expense_status(month_payment, due_date, period)
                amount = _safe_float(row.get("item_amount"), 0.0)
                group_map[gid]["items"].append({
                    "id": row["item_id"], "name": row["item_name"] or "Gider",
                    "amount": amount, "day": due_day, "due_date": due_date.isoformat(),
                    "status": status,
                    "month_payment": {
                        "id": (month_payment or {}).get("id"),
                        "payment_date": (month_payment or {}).get("payment_date"),
                        "amount": _safe_float((month_payment or {}).get("amount"), 0.0),
                        "status": (month_payment or {}).get("status"),
                    } if month_payment else None,
                    "history": history_map.get(item_id, []),
                })
            groups = list(group_map.values())
            total, paid, count, pending_count = 0.0, 0.0, 0, 0
            for group in groups:
                group_total = 0.0
                for item in group["items"]:
                    count += 1
                    group_total += _safe_float(item["amount"], 0.0)
                    total += _safe_float(item["amount"], 0.0)
                    if item["status"] == "paid":
                        paid += _safe_float(item["amount"], 0.0)
                    else:
                        pending_count += 1
                group["total_amount"] = round(group_total, 2)
            return api_response(200, {
                "month": period,
                "stats": {"total": round(total, 2), "paid": round(paid, 2), "remaining": round(max(total - paid, 0), 2), "count": count, "pending_count": pending_count},
                "data": groups,
            })
    finally:
        release_db_connection(conn)


def handle_fixed_expense_group_create(user_id, body):
    body = body or {}
    title = str(body.get("title") or "").strip()
    category_type = str(body.get("category_type") or "Diger").strip()[:80]
    if not title:
        return api_response(400, {"error": "title is required"})
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO fixed_expense_groups (user_id, title, category_type)
                VALUES (%s,%s,%s) RETURNING id, title, category_type, created_at, updated_at""",
                (user_id, title[:150], category_type),
            )
            conn.commit()
            return api_response(201, cur.fetchone())
    finally:
        release_db_connection(conn)


def handle_fixed_expense_group_update(user_id, group_id, body):
    body = body or {}
    updates, values = [], []
    if body.get("title") is not None:
        title = str(body["title"] or "").strip()
        if not title:
            return api_response(400, {"error": "title cannot be empty"})
        updates.append("title=%s"); values.append(title[:150])
    if body.get("category_type") is not None:
        updates.append("category_type=%s"); values.append(str(body["category_type"] or "Diger").strip()[:80])
    if body.get("is_active") is not None:
        is_active = _coerce_bool(body["is_active"], None)
        if is_active is None:
            return api_response(400, {"error": "is_active must be boolean"})
        updates.append("is_active=%s"); values.append(is_active)
    if not updates:
        return api_response(400, {"error": "No valid fields to update"})
    updates.append("updated_at=NOW()")
    values.extend([group_id, user_id])
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""UPDATE fixed_expense_groups SET {", ".join(updates)}
                WHERE id=%s AND user_id=%s
                RETURNING id, title, category_type, is_active, created_at, updated_at""",
                values,
            )
            updated = cur.fetchone()
            if not updated:
                return api_response(404, {"error": "Group not found"})
            conn.commit()
            return api_response(200, updated)
    finally:
        release_db_connection(conn)


def handle_fixed_expense_group_delete(user_id, group_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "UPDATE fixed_expense_groups SET is_active=FALSE, updated_at=NOW() WHERE id=%s AND user_id=%s RETURNING id",
                (group_id, user_id),
            )
            if not cur.fetchone():
                return api_response(404, {"error": "Group not found"})
            cur.execute("UPDATE fixed_expense_items SET is_active=FALSE, updated_at=NOW() WHERE group_id=%s AND user_id=%s", (group_id, user_id))
            conn.commit()
            return api_response(200, {"message": "Deleted"})
    finally:
        release_db_connection(conn)


def handle_fixed_expense_item_create(user_id, body):
    body = body or {}
    group_id = body.get("group_id")
    name = str(body.get("name") or "").strip()
    amount = _safe_float(body.get("amount"), None)
    due_day = body.get("day")
    if not group_id or not name or amount is None:
        return api_response(400, {"error": "group_id, name and amount are required"})
    if amount <= 0:
        return api_response(400, {"error": "amount must be greater than 0"})
    try:
        due_day = int(due_day)
        if due_day < 1 or due_day > 31:
            raise ValueError()
    except Exception:
        return api_response(400, {"error": "day must be between 1 and 31"})
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM fixed_expense_groups WHERE id=%s AND user_id=%s AND is_active=TRUE", (group_id, user_id))
            if not cur.fetchone():
                return api_response(404, {"error": "Group not found"})
            cur.execute(
                """INSERT INTO fixed_expense_items (group_id, user_id, name, amount, due_day)
                VALUES (%s,%s,%s,%s,%s) RETURNING id, group_id, name, amount, due_day, created_at, updated_at""",
                (group_id, user_id, name[:150], amount, due_day),
            )
            conn.commit()
            return api_response(201, cur.fetchone())
    finally:
        release_db_connection(conn)


def handle_fixed_expense_item_update(user_id, item_id, body):
    body = body or {}
    updates, values = [], []
    if body.get("name") is not None:
        name = str(body["name"] or "").strip()
        if not name:
            return api_response(400, {"error": "name cannot be empty"})
        updates.append("name=%s"); values.append(name[:150])
    if body.get("amount") is not None:
        amount = _safe_float(body["amount"], None)
        if amount is None or amount <= 0:
            return api_response(400, {"error": "amount must be greater than 0"})
        updates.append("amount=%s"); values.append(amount)
    if body.get("day") is not None:
        try:
            due_day = int(body["day"])
            if due_day < 1 or due_day > 31:
                raise ValueError()
            updates.append("due_day=%s"); values.append(due_day)
        except Exception:
            return api_response(400, {"error": "day must be between 1 and 31"})
    if body.get("is_active") is not None:
        is_active = _coerce_bool(body["is_active"], None)
        if is_active is None:
            return api_response(400, {"error": "is_active must be boolean"})
        updates.append("is_active=%s"); values.append(is_active)
    if not updates:
        return api_response(400, {"error": "No valid fields to update"})
    updates.append("updated_at=NOW()")
    values.extend([item_id, user_id])
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""UPDATE fixed_expense_items SET {", ".join(updates)}
                WHERE id=%s AND user_id=%s
                RETURNING id, group_id, name, amount, due_day, is_active, created_at, updated_at""",
                values,
            )
            updated = cur.fetchone()
            if not updated:
                return api_response(404, {"error": "Item not found"})
            conn.commit()
            return api_response(200, updated)
    finally:
        release_db_connection(conn)


def handle_fixed_expense_item_delete(user_id, item_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("UPDATE fixed_expense_items SET is_active=FALSE, updated_at=NOW() WHERE id=%s AND user_id=%s RETURNING id", (item_id, user_id))
            if not cur.fetchone():
                return api_response(404, {"error": "Item not found"})
            conn.commit()
            return api_response(200, {"message": "Deleted"})
    finally:
        release_db_connection(conn)


def handle_fixed_expense_payment_upsert(user_id, item_id, body):
    body = body or {}
    status = str(body.get("status") or "paid").strip().lower()
    if status not in {"paid", "pending"}:
        return api_response(400, {"error": "status must be paid or pending"})
    month = body.get("month")
    payment_date_raw = body.get("payment_date")
    note = re.sub(r"\s+", " ", str(body.get("note") or "")).strip()[:280]
    source = str(body.get("source") or "manual").strip()[:40]
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT i.id, i.amount, i.due_day
                FROM fixed_expense_items i
                JOIN fixed_expense_groups g ON g.id=i.group_id
                WHERE i.id=%s AND i.user_id=%s AND i.is_active=TRUE AND g.is_active=TRUE""",
                (item_id, user_id),
            )
            item = cur.fetchone()
            if not item:
                return api_response(404, {"error": "Item not found"})
            if payment_date_raw:
                try:
                    payment_date = datetime.strptime(str(payment_date_raw), "%Y-%m-%d").date()
                except Exception:
                    return api_response(400, {"error": "payment_date must be YYYY-MM-DD"})
            elif month:
                payment_date = _resolve_due_date_for_period(month, item.get("due_day") or 1)
            else:
                payment_date = date.today()
            amount = _safe_float(body.get("amount"), _safe_float(item.get("amount"), 0.0))
            if amount <= 0:
                return api_response(400, {"error": "amount must be greater than 0"})
            cur.execute(
                """INSERT INTO fixed_expense_payments (item_id, user_id, payment_date, amount, status, note, source)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (item_id, payment_date) DO UPDATE SET
                    amount=EXCLUDED.amount, status=EXCLUDED.status, note=EXCLUDED.note, source=EXCLUDED.source, updated_at=NOW()
                RETURNING id, item_id, payment_date, amount, status, note, source, created_at, updated_at""",
                (item_id, user_id, payment_date, amount, status, note, source),
            )
            conn.commit()
            return api_response(200, cur.fetchone())
    finally:
        release_db_connection(conn)
