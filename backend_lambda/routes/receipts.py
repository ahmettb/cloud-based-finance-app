import base64
import json
import re
import uuid
from datetime import date, datetime

from psycopg2.extras import RealDictCursor

from config import (
    BEDROCK_MODEL_ID, CATEGORIES, OCR_MAX_FILE_BYTES, S3_BUCKET_NAME,
    SUPPORTED_UPLOAD_TYPES, bedrock_runtime, logger, s3_client,
)
from db import get_db_connection, release_db_connection
from helpers import (
    _build_receipt_image_url, _determine_category, _fix_date,
    _resolve_category_id, _safe_float, api_response, emit_bedrock_metrics,
    get_text_embedding, _json_default,
)


def handle_receipts_list(user_id, params):
    params = params or {}
    limit = min(max(int(params.get("limit", 50)), 1), 200)
    offset = max(int(params.get("offset", 0)), 0)
    filters = ["user_id = %s"]
    values = [user_id]
    status = params.get("status")
    if status:
        filters.append("status = %s")
        values.append(status)
    category_id = params.get("category_id")
    if category_id:
        try:
            filters.append("category_id = %s")
            values.append(int(category_id))
        except Exception:
            pass
    start_date = _fix_date(params.get("start_date"))
    if start_date:
        filters.append("receipt_date >= %s")
        values.append(start_date)
    end_date = _fix_date(params.get("end_date"))
    if end_date:
        filters.append("receipt_date <= %s")
        values.append(end_date)
    where_sql = " AND ".join(filters)
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""SELECT id, file_url, status, merchant_name, receipt_date, total_amount, category_id, created_at, updated_at
                FROM receipts WHERE {where_sql}
                ORDER BY COALESCE(receipt_date, created_at) DESC, created_at DESC
                LIMIT %s OFFSET %s""",
                values + [limit, offset],
            )
            rows = cur.fetchall()
            for row in rows:
                row["category"] = CATEGORIES.get(row.get("category_id"), "Diğer")
            cur.execute(f"SELECT COUNT(*) AS total FROM receipts WHERE {where_sql}", values)
            total = cur.fetchone()["total"]
        return api_response(200, {"data": rows, "pagination": {"limit": limit, "offset": offset, "total": total}})
    finally:
        release_db_connection(conn)


def handle_receipt_detail(user_id, receipt_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT id, user_id, file_url, status, merchant_name, receipt_date, total_amount,
                       category_id, payment_method, description, created_at, updated_at
                FROM receipts WHERE id=%s AND user_id=%s""",
                (receipt_id, user_id),
            )
            receipt = cur.fetchone()
            if not receipt:
                return api_response(404, {"error": "Receipt not found"})
            cur.execute(
                "SELECT id, item_name, quantity, unit_price, total_price FROM receipt_items WHERE receipt_id=%s ORDER BY id ASC",
                (receipt_id,),
            )
            receipt["items"] = cur.fetchall()
            receipt["category"] = CATEGORIES.get(receipt.get("category_id"), "Diğer")
            receipt["image_url"] = _build_receipt_image_url(receipt.get("file_url"))
            if receipt["image_url"]:
                receipt["file_url"] = receipt["image_url"]
            elif str(receipt.get("file_url") or "").startswith("manual/"):
                receipt["file_url"] = None
            return api_response(200, receipt)
    finally:
        release_db_connection(conn)


def handle_receipt_update(user_id, receipt_id, body):
    body = body or {}
    allowed = {
        "merchant_name": body.get("merchant_name"),
        "total_amount": _safe_float(body.get("total_amount"), None),
        "receipt_date": body.get("receipt_date"),
        "category_id": body.get("category_id"),
        "payment_method": body.get("payment_method") or body.get("paymentMethod"),
        "description": body.get("description"),
    }
    updates, values = [], []
    if allowed["merchant_name"] is not None:
        updates.append("merchant_name=%s")
        values.append(str(allowed["merchant_name"])[:255])
    if allowed["total_amount"] is not None:
        updates.append("total_amount=%s")
        values.append(allowed["total_amount"])
    if allowed["receipt_date"]:
        updates.append("receipt_date=%s")
        values.append(allowed["receipt_date"])
    if allowed["category_id"] is not None:
        try:
            cid = int(allowed["category_id"])
            if cid in CATEGORIES:
                updates.append("category_id=%s")
                values.append(cid)
        except Exception:
            pass
    if allowed.get("payment_method") is not None:
        updates.append("payment_method=%s")
        values.append(str(allowed["payment_method"])[:40])
    if allowed.get("description") is not None:
        updates.append("description=%s")
        values.append(str(allowed["description"])[:500])
    if not updates:
        return api_response(400, {"error": "No valid fields to update"})
    updates.append("updated_at=NOW()")
    if allowed["merchant_name"] or allowed["total_amount"] or allowed["category_id"] or allowed["description"]:
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT merchant_name, total_amount, category_id, description, receipt_date FROM receipts WHERE id=%s", (receipt_id,))
                existing = cur.fetchone()
                if existing:
                    m = allowed["merchant_name"] or existing["merchant_name"]
                    a = allowed["total_amount"] or existing["total_amount"]
                    c = CATEGORIES.get(allowed["category_id"] or existing["category_id"], "Diğer")
                    d = allowed["description"] or existing["description"] or ""
                    rd = allowed["receipt_date"] or existing["receipt_date"]
                    embed_text = f"Tarih: {rd}. Mekan: {m}. Tutar: {a} TL. Kategori: {c}. Açıklama: {d}"
                    vec = get_text_embedding(embed_text)
                    if vec:
                        updates.append("embedding=%s")
                        values.append(json.dumps(vec))
        except Exception as e:
            logger.error(f"Error preparing embedding update: {e}")
        finally:
            release_db_connection(conn)
    values.extend([receipt_id, user_id])
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""UPDATE receipts SET {', '.join(updates)}
                WHERE id=%s AND user_id=%s
                RETURNING id, merchant_name, total_amount, receipt_date, category_id, status, updated_at""",
                values,
            )
            row = cur.fetchone()
            if not row:
                return api_response(404, {"error": "Receipt not found"})
            conn.commit()
            row["category"] = CATEGORIES.get(row.get("category_id"), "Diğer")
            return api_response(200, row)
    finally:
        release_db_connection(conn)


def handle_receipt_items(user_id, receipt_id, method, body, item_id=None):
    body = body or {}
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM receipts WHERE id=%s AND user_id=%s", (receipt_id, user_id))
            if not cur.fetchone():
                return api_response(404, {"error": "Receipt not found"})
            if method == "POST":
                item_name = str(body.get("item_name") or "").strip()
                quantity = max(int(_safe_float(body.get("quantity"), 1)), 1)
                unit_price = _safe_float(body.get("unit_price"), 0.0)
                total_price = _safe_float(body.get("total_price"), None) or round(unit_price * quantity, 2)
                if not item_name:
                    return api_response(400, {"error": "item_name is required"})
                cur.execute(
                    """INSERT INTO receipt_items (receipt_id, item_name, quantity, unit_price, total_price)
                    VALUES (%s,%s,%s,%s,%s)
                    RETURNING id, receipt_id, item_name, quantity, unit_price, total_price""",
                    (receipt_id, item_name[:255], quantity, unit_price, total_price),
                )
                conn.commit()
                return api_response(201, cur.fetchone())
            if method in {"PUT", "PATCH"} and item_id:
                sets, vals = [], []
                if body.get("item_name") is not None:
                    sets.append("item_name=%s"); vals.append(str(body["item_name"])[:255])
                if body.get("quantity") is not None:
                    sets.append("quantity=%s"); vals.append(max(int(_safe_float(body["quantity"], 1)), 1))
                if body.get("unit_price") is not None:
                    sets.append("unit_price=%s"); vals.append(_safe_float(body["unit_price"], 0.0))
                if body.get("total_price") is not None:
                    sets.append("total_price=%s"); vals.append(_safe_float(body["total_price"], 0.0))
                if not sets:
                    return api_response(400, {"error": "No valid fields"})
                vals.extend([item_id, receipt_id])
                cur.execute(
                    f"""UPDATE receipt_items SET {', '.join(sets)}
                    WHERE id=%s AND receipt_id=%s
                    RETURNING id, receipt_id, item_name, quantity, unit_price, total_price""",
                    vals,
                )
                updated = cur.fetchone()
                if not updated:
                    return api_response(404, {"error": "Item not found"})
                conn.commit()
                return api_response(200, updated)
            if method == "DELETE" and item_id:
                cur.execute("DELETE FROM receipt_items WHERE id=%s AND receipt_id=%s RETURNING id", (item_id, receipt_id))
                if not cur.fetchone():
                    return api_response(404, {"error": "Item not found"})
                conn.commit()
                return api_response(200, {"deleted": True})
            return api_response(405, {"error": "Method not allowed"})
    finally:
        release_db_connection(conn)


def handle_receipt_process(user_id, receipt_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, file_url, status FROM receipts WHERE id=%s AND user_id=%s", (receipt_id, user_id))
            receipt = cur.fetchone()
            if not receipt:
                return api_response(404, {"error": "Receipt not found"})
            if receipt["status"] == "completed":
                return api_response(200, {"message": "Receipt already processed"})
            cur.execute("UPDATE receipts SET status='processing', updated_at=NOW() WHERE id=%s", (receipt_id,))
            conn.commit()
            try:
                s3_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=receipt["file_url"])
                file_bytes = s3_obj["Body"].read()
            except Exception as exc:
                cur.execute("UPDATE receipts SET status='failed', updated_at=NOW() WHERE id=%s", (receipt_id,))
                conn.commit()
                logger.error(f"S3 file read failed for receipt {receipt_id}: {exc}")
                return api_response(500, {"error": "File read failed"})
            if len(file_bytes) > OCR_MAX_FILE_BYTES:
                cur.execute("UPDATE receipts SET status='failed', updated_at=NOW() WHERE id=%s", (receipt_id,))
                conn.commit()
                return api_response(413, {"error": "File too large for OCR", "max_bytes": OCR_MAX_FILE_BYTES, "current_bytes": len(file_bytes)})
            if receipt["file_url"].lower().endswith(".pdf"):
                media_type = "application/pdf"
            elif receipt["file_url"].lower().endswith(".png"):
                media_type = "image/png"
            else:
                media_type = "image/jpeg"
            image_b64 = base64.b64encode(file_bytes).decode("utf-8")
            system_prompt = "You are a financial AI assistant. Analyze the receipt image and extraction structured data. Output ONLY raw JSON. No markdown formatting, no code blocks, no conversational text."
            user_prompt = (
                "Extract JSON only with fields: merchant_name,total_amount,receipt_date(YYYY-MM-DD),"
                "items[{name,price}],currency(default TRY),category_id(1-8). "
                "Categories:1 Market,2 Restoran,3 Kafe,4 Eğlence,5 Fatura,6 Giyim,7 Ulaşım,8 Diğer. "
                "No markdown or extra text."
            )
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1500,
                "system": system_prompt,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text", "text": user_prompt},
                ]}],
            }
            raw_text = "{}"
            try:
                resp = bedrock_runtime.invoke_model(modelId=BEDROCK_MODEL_ID, body=json.dumps(payload))
                resp_body = json.loads(resp["body"].read())
                _usage = resp_body.get("usage", {})
                emit_bedrock_metrics("ocr", _usage.get("input_tokens", 0), _usage.get("output_tokens", 0))
                content_block = resp_body.get("content", [])
                if content_block and isinstance(content_block, list):
                    raw_text = content_block[0].get("text", "{}")
                else:
                    logger.error(f"Unexpected Bedrock response format: {resp_body}")
            except Exception as exc:
                logger.error(f"Bedrock OCR invoke failed: {exc}", exc_info=True)
                cur.execute("UPDATE receipts SET status='failed', last_error=%s, updated_at=NOW() WHERE id=%s", (str(exc), receipt_id))
                conn.commit()
                return api_response(500, {"error": "AI service error"})
            ocr_data = {}
            try:
                clean_text = raw_text.strip()
                if clean_text.startswith("```json"): clean_text = clean_text[7:]
                if clean_text.startswith("```"): clean_text = clean_text[3:]
                if clean_text.endswith("```"): clean_text = clean_text[:-3]
                clean_text = clean_text.strip()
                start_idx = clean_text.find('{')
                end_idx = clean_text.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    ocr_data = json.loads(clean_text[start_idx:end_idx + 1])
                else:
                    ocr_data = json.loads(clean_text)
            except Exception:
                logger.error(f"OCR JSON parse failed. Raw text: {raw_text[:1000]}")
            if not ocr_data:
                cur.execute("UPDATE receipts SET status='failed', updated_at=NOW() WHERE id=%s", (receipt_id,))
                conn.commit()
                return api_response(422, {"error": "OCR parse failed", "raw_response": raw_text[:500]})
            merchant = str(ocr_data.get("merchant_name") or "Bilinmiyor")[:255]
            amount = _safe_float(ocr_data.get("total_amount"), 0.0)
            r_date = ocr_data.get("receipt_date") or date.today().isoformat()
            items = ocr_data.get("items") or []
            currency = str(ocr_data.get("currency") or "TRY")[:10]
            category_id = _determine_category(merchant, items=items, ai_suggested_id=ocr_data.get("category_id"))
            cur.execute(
                """UPDATE receipts SET merchant_name=%s, total_amount=%s, receipt_date=%s, category_id=%s,
                    currency=%s, status='completed', updated_at=NOW() WHERE id=%s""",
                (merchant, amount, r_date, category_id, currency, receipt_id),
            )
            cur.execute("DELETE FROM receipt_items WHERE receipt_id=%s", (receipt_id,))
            items_text = []
            for item in items[:30]:
                item_n = str(item.get("name") or "")[:255]
                item_p = _safe_float(item.get("price"))
                cur.execute("INSERT INTO receipt_items (receipt_id, item_name, total_price) VALUES (%s,%s,%s)", (receipt_id, item_n, item_p))
                if item_n and item_p:
                    items_text.append(f"{item_n} ({item_p} {currency})")
            cat_name = CATEGORIES.get(category_id, "Diğer")
            embed_text = f"Tarih: {r_date}. Mekan: {merchant}. Tutar: {amount} {currency}. Kategori: {cat_name}. Kalemler: {', '.join(items_text)}"
            vec = get_text_embedding(embed_text)
            if vec:
                cur.execute("UPDATE receipts SET embedding=%s WHERE id=%s", (json.dumps(vec), receipt_id))
            conn.commit()
            return api_response(200, {
                "receipt_id": receipt_id, "status": "completed", "merchant_name": merchant,
                "total_amount": amount, "receipt_date": r_date, "category_id": category_id,
                "category_name": cat_name, "items_count": min(len(items), 30),
                "currency": currency, "ocr_data": ocr_data,
            })
    except Exception as exc:
        logger.error(f"Receipt process failed: {exc}", exc_info=True)
        return api_response(500, {"error": "Receipt processing failed"})
    finally:
        release_db_connection(conn)


def handle_receipt_delete(user_id, receipt_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM receipts WHERE id=%s AND user_id=%s RETURNING file_url", (receipt_id, user_id))
            row = cur.fetchone()
            if not row:
                return api_response(404, {"error": "Receipt not found"})
            conn.commit()
            try:
                s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=row[0])
            except Exception:
                pass
            return api_response(200, {"message": "Deleted"})
    finally:
        release_db_connection(conn)


def handle_upload_init(user_id, body):
    body = body or {}
    filename = body.get("filename")
    ctype = body.get("content_type")
    if not filename or not ctype:
        return api_response(400, {"error": "filename and content_type are required"})
    ext = SUPPORTED_UPLOAD_TYPES.get(ctype)
    if not ext:
        return api_response(400, {"error": "Unsupported content_type"})
    rid = str(uuid.uuid4())
    key = f"users/{user_id}/receipts/{rid}.{ext}"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO receipts (id, user_id, file_url, status) VALUES (%s,%s,%s,'pending')", (rid, user_id, key))
            conn.commit()
    finally:
        release_db_connection(conn)
    upload_url = s3_client.generate_presigned_url("put_object", Params={"Bucket": S3_BUCKET_NAME, "Key": key, "ContentType": ctype}, ExpiresIn=600)
    return api_response(200, {"upload_url": upload_url, "receipt_id": rid, "s3_key": key})


def handle_manual_receipt_create(user_id, body):
    body = body or {}
    merchant_name = str(body.get("merchant_name") or "").strip()
    total_amount = _safe_float(body.get("total_amount"), None)
    receipt_date = body.get("receipt_date") or date.today().isoformat()
    currency = str(body.get("currency") or "TRY").strip().upper()[:10]
    payment_method = str(body.get("payment_method") or body.get("paymentMethod") or "").strip()[:40] or None
    description = str(body.get("description") or "").strip()[:500] or None
    category_id = _resolve_category_id(
        raw_category_id=body.get("category_id"),
        raw_category_name=body.get("category_name"),
        merchant_name=merchant_name,
    )
    if not merchant_name:
        return api_response(400, {"error": "merchant_name is required"})
    if total_amount is None or total_amount <= 0:
        return api_response(400, {"error": "total_amount must be greater than 0"})
    try:
        datetime.strptime(str(receipt_date), "%Y-%m-%d")
    except Exception:
        return api_response(400, {"error": "receipt_date must be YYYY-MM-DD"})
    rid = str(uuid.uuid4())
    manual_key = f"manual/{user_id}/{rid}.json"
    cat_name = CATEGORIES.get(category_id, "Diğer")
    embed_text = f"Tarih: {receipt_date}. Mekan: {merchant_name}. Tutar: {total_amount} {currency}. Kategori: {cat_name}. Açıklama: {description or ''}"
    vec = get_text_embedding(embed_text)
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if vec:
                cur.execute(
                    """INSERT INTO receipts (id, user_id, file_url, status, merchant_name, receipt_date, total_amount, category_id, currency, payment_method, description, embedding)
                    VALUES (%s,%s,%s,'completed',%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id, merchant_name, receipt_date, total_amount, category_id, status, payment_method, description, created_at, updated_at""",
                    (rid, user_id, manual_key, merchant_name[:255], receipt_date, total_amount, category_id, currency, payment_method, description, json.dumps(vec)),
                )
            else:
                cur.execute(
                    """INSERT INTO receipts (id, user_id, file_url, status, merchant_name, receipt_date, total_amount, category_id, currency, payment_method, description)
                    VALUES (%s,%s,%s,'completed',%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id, merchant_name, receipt_date, total_amount, category_id, status, payment_method, description, created_at, updated_at""",
                    (rid, user_id, manual_key, merchant_name[:255], receipt_date, total_amount, category_id, currency, payment_method, description),
                )
            created = cur.fetchone()
            conn.commit()
            created["category"] = cat_name
            created["source"] = "manual"
            return api_response(201, created)
    finally:
        release_db_connection(conn)


def handle_smart_extract(user_id, body):
    body = body or {}
    text = body.get("text", "").strip()
    if not text:
        return api_response(400, {"error": "Text is required"})
    today = date.today().isoformat()
    cat_list = ",".join(CATEGORIES.values())
    normalized_text = re.sub(r"\s+", " ", text).strip()[:350]
    prompt = (
        f"Date:{today}; Input:{normalized_text}; Cats:{cat_list},Diğer. "
        "Return ONLY valid JSON with merchant_name,total_amount,receipt_date(YYYY-MM-DD),"
        "category_name,description. Use correct Turkish characters. No markdown."
    )
    try:
        response = bedrock_runtime.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 300, "temperature": 0}
        )
        _usage = response.get("usage", {})
        emit_bedrock_metrics("smart_extract", _usage.get("inputTokens", 0), _usage.get("outputTokens", 0))
        output_text = response["output"]["message"]["content"][0]["text"].strip()
        start = output_text.find("{")
        end = output_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = re.sub(r',\s*}', '}', output_text[start:end + 1])
            try:
                return api_response(200, json.loads(json_str))
            except json.JSONDecodeError:
                try:
                    import ast
                    return api_response(200, ast.literal_eval(json_str))
                except Exception:
                    logger.error(f"Smart extract JSON parse error: {json_str[:500]}")
                    return api_response(500, {"error": "Invalid JSON from AI", "raw": output_text})
        return api_response(500, {"error": "No JSON found in AI response"})
    except Exception as e:
        logger.error(f"Smart extract failed: {e}", exc_info=True)
        return api_response(500, {"error": "Smart extraction failed"})
