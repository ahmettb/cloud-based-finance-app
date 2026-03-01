import csv
import io
import uuid

from psycopg2.extras import RealDictCursor

from config import CATEGORIES, S3_BUCKET_NAME, s3_client
from db import get_db_connection, release_db_connection
from helpers import _safe_float, api_response


def handle_export_data(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT receipt_date, merchant_name, total_amount, category_id, status
                FROM receipts WHERE user_id=%s ORDER BY COALESCE(receipt_date, created_at) DESC""",
                (user_id,),
            )
            rows = cur.fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Merchant", "Amount", "Category", "Status"])
        for row in rows:
            writer.writerow([
                row.get("receipt_date"), row.get("merchant_name"),
                _safe_float(row.get("total_amount")),
                CATEGORIES.get(row.get("category_id"), "Diğer"), row.get("status"),
            ])
        key = f"exports/{user_id}/{uuid.uuid4()}.csv"
        s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=key, Body=output.getvalue().encode("utf-8"), ContentType="text/csv")
        download_url = s3_client.generate_presigned_url("get_object", Params={"Bucket": S3_BUCKET_NAME, "Key": key}, ExpiresIn=600)
        return api_response(200, {"download_url": download_url, "key": key})
    finally:
        release_db_connection(conn)
