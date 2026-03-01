import json

from psycopg2.extras import RealDictCursor

from config import CATEGORIES, bedrock_runtime, logger, get_langfuse
from db import get_db_connection, release_db_connection
from helpers import api_response, emit_bedrock_metrics, get_text_embedding


def handle_ai_chat(user_id, body):
    body = body or {}
    user_query = str(body.get("query") or "").strip()
    if not user_query:
        return api_response(400, {"error": "Query is required"})
    query_embedding = get_text_embedding(user_query)
    if not query_embedding:
        return api_response(500, {"error": "Failed to generate embedding for query"})
    conn = get_db_connection()
    context_docs = []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT TO_CHAR(receipt_date, 'YYYY-MM') as month, category_id, SUM(total_amount) as total
                FROM receipts WHERE user_id = %s AND status != 'deleted' AND receipt_date >= CURRENT_DATE - INTERVAL '3 months'
                GROUP BY 1, 2 ORDER BY 1 DESC""",
                (user_id,)
            )
            cat_rows = cur.fetchall()
            if cat_rows:
                context_docs.append("--- GENEL KATEGORİ ÖZETİ (Son 3 Ay) ---")
                for row in cat_rows:
                    cat_name = CATEGORIES.get(row.get('category_id'), "Diğer")
                    context_docs.append(f"Ay: {row['month'] or 'Bilinmeyen'}, Kategori: {cat_name}, Toplam: {row['total']} TL")
                context_docs.append("---------------------------------------")
            cur.execute("SELECT category_name, amount FROM budgets WHERE user_id = %s", (user_id,))
            budget_rows = cur.fetchall()
            if budget_rows:
                context_docs.append("--- BÜTÇE HEDEFLERİ (Aylık Limitler) ---")
                for br in budget_rows:
                    context_docs.append(f"Kategori: {br['category_name']}, Hedef/Limit: {br['amount']} TL")
                context_docs.append("----------------------------------------")
            cur.execute("SELECT title, target_amount, current_amount, target_date FROM financial_goals WHERE user_id = %s AND status = 'active'", (user_id,))
            goal_rows = cur.fetchall()
            if goal_rows:
                context_docs.append("--- TASARRUF HEDEFLERİ ---")
                for gr in goal_rows:
                    context_docs.append(f"Süreç: {gr['title']}, Biriken: {gr['current_amount']} TL / Toplam Hedef: {gr['target_amount']} TL, Son Tarih: {gr['target_date'] or 'Belirtilmemiş'}")
                context_docs.append("--------------------------")
            cur.execute("SELECT source, amount, income_date FROM incomes WHERE user_id = %s ORDER BY income_date DESC LIMIT 5", (user_id,))
            income_rows = cur.fetchall()
            if income_rows:
                context_docs.append("--- SON VE AKTİF GELİRLER ---")
                for ir in income_rows:
                    context_docs.append(f"Kaynak: {ir['source']}, Tutar: {ir['amount']} TL, Tarih: {ir['income_date']}")
                context_docs.append("-----------------------------")
            cur.execute("SELECT name, amount, next_payment_date FROM subscriptions WHERE user_id = %s", (user_id,))
            sub_rows = cur.fetchall()
            if sub_rows:
                context_docs.append("--- GİDER YÖNETİMİ / ABONELİKLER ---")
                for sr in sub_rows:
                    context_docs.append(f"Abonelik: {sr['name']}, Tutar: {sr['amount']} TL, Sonraki Ödeme: {sr['next_payment_date'] or 'Belirtilmemiş'}")
                context_docs.append("------------------------------------")
            cur.execute(
                """SELECT id, merchant_name, total_amount, currency, receipt_date, description, category_id,
                       embedding <=> %s::vector AS distance
                FROM receipts WHERE user_id = %s AND status != 'deleted' AND embedding IS NOT NULL
                ORDER BY distance ASC LIMIT 40""",
                (json.dumps(query_embedding), user_id)
            )
            rows = cur.fetchall()
            if rows:
                context_docs.append("--- İLGİLİ HARCAMA KAYITLARI (Vektör Araması) ---")
                for r in rows:
                    desc = r.get('description') or ''
                    cat_name = CATEGORIES.get(r.get('category_id'), 'Diğer')
                    context_docs.append(f"Tarih: {r['receipt_date']}, Mekan: {r['merchant_name']}, Kategori: {cat_name}, Tutar: {r['total_amount']} {r['currency']}, Açıklama: {desc}")
    except Exception as e:
        logger.error(f"Vector search failed: {e}", exc_info=True)
        return api_response(500, {"error": "Database search failed"})
    finally:
        release_db_connection(conn)
    context_str = "\n".join(context_docs) if context_docs else "İlgili finansal veri bulunamadı."
    system_prompt_text = (
        "Sen kullanıcının kişisel finans asistanı 'ParamNerede' AI'sın. "
        "Aşağıda kullanıcının veri tabanından sistemin otomatik olarak çektiği Kategori Özetleri ve en alakalı Harcama Kayıtları verilmiştir.\n\n"
        f"KULLANICI VERİLERİ (BAĞLAM):\n{context_str}\n\n"
        "Kurallar:\n"
        "1. Çok resmi ve aşırı teknik bir dil kullanma! Sohbet havasında, cana yakın ama aynı zamanda bilgilendirici ve profesyonel ol.\n"
        "2. KISA ve ÖZ cevap ver. Maksimum 3-4 cümle. Liste gerektiriyorsa en fazla 5 madde. Asla uzun paragraf yazma.\n"
        "3. Harcama kayıtlarını listelerken Markdown madde imleri kullan, kalın yaz.\n"
        "4. Kullanıcının sorusunu SADECE yukarıdaki bağlama dayanarak yanıtla. Eğer aranan veri bağlamda yoksa, dürüstçe 'Kayıtlarında bulamadım' de, tahmin yürütme.\n"
        "5. Türkçe yanıt ver."
    )
    lf = get_langfuse()
    trace, generation = None, None
    if lf:
        trace = lf.trace(name="ai-chat-response", user_id=str(user_id))
        try:
            lf_prompt = lf.get_prompt("paramnerede-system-prompt")
            system_prompt_text = lf_prompt.compile(context_str=context_str)
        except Exception as e:
            logger.info(f"Langfuse prompt not found, using default: {e}")
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "system": system_prompt_text,
        "messages": [{"role": "user", "content": user_query}]
    }
    try:
        if trace:
            generation = trace.generation(name="claude-3-haiku", model="anthropic.claude-3-haiku-20240307-v1:0", input=payload["messages"])
        response = bedrock_runtime.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(payload), accept="application/json", contentType="application/json"
        )
        response_body = json.loads(response["body"].read())
        reply_text = ""
        content_block = response_body.get("content", [])
        if content_block and isinstance(content_block, list):
            reply_text = content_block[0].get("text", "")
        usage = response_body.get("usage", {})
        emit_bedrock_metrics("chat", usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        if generation:
            generation.end(output=reply_text, usage={"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)})
            lf.flush()
        return api_response(200, {"reply": reply_text, "context_used": len(context_docs)})
    except Exception as exc:
        logger.error(f"Bedrock chat invoke failed: {exc}", exc_info=True)
        return api_response(500, {"error": "AI response generation failed"})
