"""
llm_enricher.py — Claude LLM Enrichment Layer
===============================================
Hesaplanmış structured verileri Claude'a gönderip insanca Türkçe yorumlar alır.

Katman sorumluluğu:
  - Claude HESAPLAMA YAPMAZ, yalnızca mevcut sonuçları yorumlar
  - Her LLM çağrısı için token sayısı, maliyet ve süre loglanır
  - Hallucination tespiti ve output validasyonu yapılır
  - Başarısız olursa fallback coach döner
"""

import json
import re
import time

from ai_config import (
    BEDROCK_MODEL_ID, LLM_MAX_TOKENS, LLM_TEMPERATURE,
    LLM_INPUT_TOKEN_PRICE, LLM_OUTPUT_TOKEN_PRICE,
    get_bedrock_client, logger, log_ctx,
)
from ai_utils import compact_text


class LLMEnricher:
    """
    Statik metodlar — Claude ile zenginleştirme.
    Başarısız olursa her metod fallback döner.
    """

    # ── System Prompt ──────────────────────────────────────────────

    @staticmethod
    def get_system_prompt(persona: str = "friendly") -> str:
        persona_instructions = {
            "friendly": "Samimi, motive edici ve destekleyici bir ton kullan.",
            "professional": "Resmi, objektif, net ve ciddi bir finansal danışman dili kullan.",
            "strict": "Disiplinli, kuralcı, talepkar ve yer yer uyarıcı (sert) bir ton kullan.",
            "humorous": "Esprili, eğlenceli ve mizahi bir dil kullan, araya şakalar kat.",
        }
        tone = persona_instructions.get(persona, persona_instructions["friendly"])
        return (
            f"Türkçe kişisel finans koçusun. {tone}\n"
            "Görev: Verilen finansal verileri yorumla, kullanıcıya özgün ve akıcı bir özet sun.\n"
            "Kurallar:\n"
            "- Şablon cümleler kullanma, veriye özel konuş.\n"
            "- Harcama artmışsa uyar, azalmışsa tebrik et.\n"
            "- Yatırım tavsiyesi verme.\n"
            "- Sadece JSON döndür, başka metin ekleme.\n"
            "- Türkçe karakterleri doğru kullan.\n"
            'JSON Format:\n{"coach":{"headline":"max 60 karakter başlık",'
            '"summary":"Detaylı paragraf max 450 karakter.",'
            '"focus_areas":["odak1","odak2"]},'
            '"card_enrichments":[{"id":"card_id","title":"max 70 karakter",'
            '"summary":"max 160 karakter","actions":["aksiyon1","aksiyon2"]}]}\n'
        )

    # ── Prompt Builder ─────────────────────────────────────────────

    @staticmethod
    def _build_prompt(
        period: str,
        insights: list,
        forecast: dict,
        patterns: dict,
    ) -> str:
        """Minimal token prompt — PII içermez."""
        lines = [f"P:{compact_text(period, 12)}"]

        if forecast:
            lines.append(
                f"FX:{compact_text(forecast.get('trend'), 10)}|"
                f"est:{forecast.get('next_month_estimate', 0):.0f}|"
                f"conf:{forecast.get('confidence_score', 0)}"
            )

        vel = patterns.get("velocity")
        if vel:
            lines.append(
                f"VEL:{vel.get('days_elapsed', 0)}gun|"
                f"{vel.get('current_total', 0):.0f}TL|"
                f"proj:{vel.get('projected_month_end', 0):.0f}"
            )

        shifts = patterns.get("category_shifts")
        if shifts and shifts.get("shifts"):
            s_parts = [
                f"{compact_text(s['category'], 16)}:{s['change_pct']:+.0f}%"
                for s in shifts["shifts"][:3]
            ]
            lines.append(f"SHIFT:{'|'.join(s_parts)}")

        recurring = patterns.get("recurring_payments")
        if recurring:
            lines.append(
                f"RECUR:{recurring.get('total_monthly', 0):.0f}TL/ay|"
                f"{len(recurring.get('items', []))}adet"
            )

        for c in insights[:4]:
            cid = compact_text(c.get("id"), 24)
            pr = compact_text(c.get("priority"), 10)
            title = compact_text(c.get("title"), 48)
            summary = compact_text(c.get("summary", ""), 56)
            lines.append(f"C:{cid}|{pr}|{title}|{summary}")

        return "\n".join(lines)

    # ── Main Enrichment ────────────────────────────────────────────

    @staticmethod
    def enrich(
        period: str,
        insights: list,
        forecast: dict,
        patterns: dict,
        persona: str = "friendly",
        request_id: str = "-",
        user_id: str = "-",
    ) -> tuple:
        """
        Claude ile zenginleştirme.
        Başarısız olursa fallback coach döner.

        Returns:
            (enriched_insights, coach_dict, llm_obs_dict)
        """
        if not insights:
            return insights, LLMEnricher._fallback_coach(period, forecast), {}

        prompt_text = LLMEnricher._build_prompt(period, insights, forecast, patterns)
        system_message = LLMEnricher.get_system_prompt(persona)

        _ctx = log_ctx(
            request_id=request_id,
            user_id=user_id,
            module_name="llm_enricher",
            period=period,
        )

        llm_obs = {"status": "skipped"}

        try:
            logger.info(
                f"LLM enrichment starting — prompt={len(prompt_text)} chars",
                extra={**_ctx, "step": "llm_start"},
            )

            start = time.time()
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": LLM_MAX_TOKENS,
                "temperature": LLM_TEMPERATURE,
                "system": system_message,
                "messages": [{"role": "user", "content": prompt_text}],
            }

            client = get_bedrock_client()
            resp = client.invoke_model(
                modelId=BEDROCK_MODEL_ID, body=json.dumps(payload)
            )
            elapsed_ms = int((time.time() - start) * 1000)
            resp_body = json.loads(resp["body"].read())
            raw = resp_body["content"][0]["text"].strip()

            usage = resp_body.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cost_usd = round(
                input_tokens * LLM_INPUT_TOKEN_PRICE
                + output_tokens * LLM_OUTPUT_TOKEN_PRICE,
                6,
            )

            logger.info(
                "LLM enrichment completed",
                extra={
                    **_ctx,
                    "step": "llm_done",
                    "elapsed_ms": elapsed_ms,
                    "tokens_in": input_tokens,
                    "tokens_out": output_tokens,
                    "cost_usd": cost_usd,
                },
            )

            ai_data = LLMEnricher._parse_json(raw)
            validation = LLMEnricher._validate_output(ai_data, insights)
            hallucination_flags = LLMEnricher._detect_hallucination(
                ai_data, prompt_text, insights
            )

            llm_obs = {
                "status": "success",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "elapsed_ms": elapsed_ms,
                "cost_usd": cost_usd,
                "output_valid": validation["is_valid"],
                "validation_warnings": validation.get("warnings", []),
                "hallucination_flags": hallucination_flags,
                "raw_output_length": len(raw),
            }

            if hallucination_flags:
                logger.warning(
                    f"LLM hallucination flags detected: {hallucination_flags}",
                    extra=_ctx,
                )

            coach = ai_data.get(
                "coach", LLMEnricher._fallback_coach(period, forecast)
            )

            if validation["is_valid"]:
                enrichments = {
                    e["id"]: e
                    for e in ai_data.get("card_enrichments", [])
                    if "id" in e
                }
                for card in insights:
                    cid = card.get("id")
                    if cid in enrichments:
                        e = enrichments[cid]
                        if e.get("title"):
                            card["title"] = e["title"][:70]
                        if e.get("summary"):
                            card["summary"] = e["summary"][:180]
                        if e.get("actions"):
                            card["actions"] = [a[:100] for a in e["actions"][:3]]
            else:
                logger.warning(
                    f"LLM output validation failed, keeping raw insights: {validation['warnings']}",
                    extra=_ctx,
                )

            coach["_llm_meta"] = llm_obs
            return insights, coach, llm_obs

        except Exception as exc:
            logger.error(
                "LLM enrichment failed",
                extra={**_ctx, "step": "llm_error"},
                exc_info=True,
            )
            llm_obs = {"status": "error", "error": str(exc)}
            return insights, LLMEnricher._fallback_coach(period, forecast), llm_obs

    # ── Output Validation ──────────────────────────────────────────

    @staticmethod
    def _validate_output(ai_data: dict, original_insights: list) -> dict:
        """LLM çıktısını schema'ya göre doğrula."""
        warnings = []
        if not isinstance(ai_data, dict):
            return {"is_valid": False, "warnings": ["Output is not a dict"]}

        coach = ai_data.get("coach")
        if not coach or not isinstance(coach, dict):
            warnings.append("Missing or invalid coach object")
        else:
            if not coach.get("headline"):
                warnings.append("Coach headline empty")
            elif len(coach["headline"]) > 120:
                warnings.append(f"Coach headline too long: {len(coach['headline'])} chars")
            if not coach.get("summary"):
                warnings.append("Coach summary empty")

        enrichments = ai_data.get("card_enrichments", [])
        if enrichments:
            valid_ids = {c.get("id") for c in original_insights}
            for e in enrichments:
                if e.get("id") and e["id"] not in valid_ids:
                    warnings.append(f"Unknown card ID in enrichment: {e['id']}")

        return {"is_valid": len(warnings) <= 2, "warnings": warnings}

    # ── Hallucination Detection ────────────────────────────────────

    @staticmethod
    def _detect_hallucination(
        ai_data: dict, prompt: str, insights: list
    ) -> list:
        """Basit hallucination tespiti: prompt'ta olmayan rakamlar."""
        flags = []
        coach = ai_data.get("coach", {})
        prompt_numbers = set(re.findall(r"\d+", prompt))

        for field in ["headline", "summary"]:
            text = coach.get(field, "")
            if text:
                text_numbers = re.findall(r"\d{3,}", text)
                for num in text_numbers:
                    if num not in prompt_numbers:
                        is_derivation = False
                        for pn in prompt_numbers:
                            try:
                                ratio = int(num) / max(int(pn), 1)
                                if ratio in (12, 52, 365, 0.5, 2):
                                    is_derivation = True
                                    break
                            except (ValueError, ZeroDivisionError):
                                pass
                        if not is_derivation:
                            flags.append(
                                f"Possible fabricated number '{num}' in coach.{field}"
                            )
        return flags

    # ── JSON Parser ────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw_text: str) -> dict:
        """LLM çıktısında JSON bul ve parse et."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse LLM output as JSON: {text[:200]}")
        return {}

    # ── Fallback Coach ─────────────────────────────────────────────

    @staticmethod
    def _fallback_coach(period: str, forecast: dict | None) -> dict:
        """LLM başarısız olursa basit fallback coach."""
        headline = f"{period} analizi tamamlandı."
        if forecast and forecast.get("trend") == "up":
            headline = "Dikkat: harcamalar artış eğiliminde!"
        elif forecast and forecast.get("trend") == "down":
            headline = "Harcamalarınız düşüş eğiliminde."

        return {
            "headline": headline,
            "summary": f"{period} dönemine ait finansal analiz sonuçları hazır.",
            "focus_areas": ["Bütçe takibi", "Harcama trendi", "Tasarruf fırsatları"],
        }
