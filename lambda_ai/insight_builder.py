"""
insight_builder.py — Structured Insight Card Generator
=======================================================
Anomali, tahmin ve pattern sonuçlarından kullanıcıya gösterilecek
structured insight kartları üretir.

Her kart şu alanları içerir:
  id, type, priority, title, summary, confidence, evidence[], actions[]
"""

import statistics

from ai_utils import sf, uid, confidence as calc_confidence
from ai_config import ANOMALY_Z_THRESHOLD


class InsightBuilder:
    """
    Tüm metodlar statik — sınıf sadece namespace için kullanılır.
    Her from_* metodu bir kart listesi döner.
    """

    @staticmethod
    def _next_id(prefix: str) -> str:
        """Thread-safe UUID tabanlı kart ID'si."""
        return uid(prefix)

    # ── Anomalies → Cards ─────────────────────────────────────────

    @staticmethod
    def from_anomalies(anomalies: list, period: str) -> list:
        """Anomali listesinden insight kartları üretir."""
        if not anomalies:
            return []
        cards = []
        for a in anomalies[:5]:
            actions = [
                f"{a['merchant']} harcamasını gözden geçirin, gerekli mi değerlendirin.",
                "Benzer tutardaki geçmiş işlemleri karşılaştırın.",
            ]
            if a.get("z_score", 0) > 3:
                actions.append(
                    "Bu işlem çok yüksek sapma gösteriyor, hatalı giriş olabilir."
                )
            cards.append(
                {
                    "id": InsightBuilder._next_id("anomaly"),
                    "type": "anomaly_detection",
                    "priority": a.get("severity", "MEDIUM"),
                    "title": f"Olağandışı harcama: {a['merchant']}",
                    "summary": (
                        f"{a['merchant']}'de {a['amount']:.0f} TL harcama tespit edildi. "
                        f"Ortalamadan {a['z_score']:.1f}x sapma ({a['detection_method']})."
                    ),
                    "confidence": calc_confidence(
                        10, min(a["z_score"] / 4, 1.0)
                    ),
                    "explanation": {
                        "reason": f"{a['detection_method']} ile tespit edildi",
                        "data_points": [
                            f"Tutar: {a['amount']:.0f} TL",
                            f"Z-skor: {a['z_score']:.1f} (eşik: {ANOMALY_Z_THRESHOLD})",
                            f"Kategori: {a.get('category', '?')}",
                        ],
                        "detection_method": a["detection_method"],
                    },
                    "evidence": [
                        {"metric": "tutar", "value": a["amount"], "unit": "TL"},
                        {"metric": "z_score", "value": a["z_score"], "unit": ""},
                    ],
                    "actions": actions,
                }
            )
        return cards

    # ── Forecast → Card ───────────────────────────────────────────

    @staticmethod
    def from_forecast(forecast: dict, period: str) -> list:
        """Tahmin sonucundan insight kartı üretir."""
        if not forecast or forecast.get("next_month_estimate", 0) <= 0:
            return []
        trend_text = {
            "up": "Artış eğiliminde",
            "down": "Düşüş eğiliminde",
            "stable": "Stabil görünüyor",
        }
        trend = forecast.get("trend", "stable")
        actions: list = []
        if trend == "up":
            actions = [
                "Bütçe limitlerini bu ay için gözden geçirin.",
                "En çok artan kategoriyi tespit edip kısıntı yapın.",
            ]
        elif trend == "down":
            actions = [
                "Tasarruf hedefinizi artırabilirsiniz.",
                "Düşüş trendini korumak için mevcut alışkanlıkları sürdürün.",
            ]
        else:
            actions = [
                "Harcama dengenizi koruyun, bütçe takibine devam edin."
            ]
        return [
            {
                "id": InsightBuilder._next_id("forecast"),
                "type": "budget_forecast",
                "priority": "HIGH" if trend == "up" else "MEDIUM",
                "title": f"Gelecek ay tahmini: {forecast['next_month_estimate']:.0f} TL",
                "summary": (
                    f"Harcamalar {trend_text.get(trend, 'stabil')}. "
                    f"Güven skoru: %{forecast.get('confidence_score', 50)}."
                ),
                "confidence": forecast.get("confidence_score", 50),
                "evidence": [
                    {
                        "metric": "tahmin",
                        "value": forecast["next_month_estimate"],
                        "unit": "TL",
                    },
                    {
                        "metric": "trend",
                        "value": forecast.get("trend_pct", 0),
                        "unit": "%",
                    },
                ],
                "actions": actions,
            }
        ]

    # ── Patterns → Cards ──────────────────────────────────────────

    @staticmethod
    def from_patterns(patterns: dict, period: str) -> list:
        """Pattern sonuçlarından insight kartları üretir."""
        cards = []

        # Velocity
        velocity = patterns.get("velocity")
        if velocity and velocity.get("elapsed_pct", 0) > 0:
            v = velocity
            cards.append(
                {
                    "id": InsightBuilder._next_id("velocity"),
                    "type": "spending_summary",
                    "priority": (
                        "HIGH"
                        if v.get("elapsed_pct", 0) < 50
                        and v.get("current_total", 0)
                        > v.get("projected_month_end", 0) * 0.6
                        else "MEDIUM"
                    ),
                    "title": f"Harcama hızı: {v.get('days_elapsed', 0)} günde {v.get('current_total', 0):.0f} TL",
                    "summary": (
                        f"Ayın %{v.get('elapsed_pct', 0):.0f}'i geçti. "
                        f"Günlük ortalama {v.get('daily_avg', 0):.0f} TL. "
                        f"Ay sonu tahmini: {v.get('projected_month_end', 0):.0f} TL."
                    ),
                    "confidence": calc_confidence(v.get("days_elapsed", 5), 0.5),
                    "evidence": [
                        {
                            "metric": "gunluk_ort",
                            "value": v.get("daily_avg", 0),
                            "unit": "TL",
                        },
                        {
                            "metric": "ay_sonu",
                            "value": v.get("projected_month_end", 0),
                            "unit": "TL",
                        },
                    ],
                    "actions": [],
                }
            )

        # Day-of-week
        dow = patterns.get("day_distribution")
        if dow:
            insight_type = dow.get("insight", "balanced")
            if insight_type != "balanced":
                cards.append(
                    {
                        "id": InsightBuilder._next_id("dow"),
                        "type": "trend_analysis",
                        "priority": "LOW",
                        "title": f"En çok harcama günü: {dow.get('peak_day', '')}",
                        "summary": f"Hafta sonu harcamalarınız toplamın %{dow.get('weekend_pct', 0)}'i.",
                        "confidence": calc_confidence(20, 0.3),
                        "evidence": [
                            {
                                "metric": "hafta_sonu_yuzde",
                                "value": dow.get("weekend_pct", 0),
                                "unit": "%",
                            }
                        ],
                        "actions": [],
                    }
                )

        # Category shifts
        shifts = patterns.get("category_shifts")
        if shifts and shifts.get("shifts"):
            for s in shifts["shifts"][:3]:
                direction_label = "arttı" if s["direction"] == "up" else "azaldı"
                cards.append(
                    {
                        "id": InsightBuilder._next_id("shift"),
                        "type": "category_breakdown",
                        "priority": s.get("severity", "MEDIUM"),
                        "title": f"{s['category']} harcaması %{abs(s['change_pct']):.0f} {direction_label}",
                        "summary": (
                            f"Önceki ayların ortalaması {s['previous_avg']:.0f} TL, "
                            f"bu ay {s['current']:.0f} TL."
                        ),
                        "confidence": calc_confidence(
                            8, abs(s["change_pct"]) / 100
                        ),
                        "evidence": [
                            {
                                "metric": "onceki_ort",
                                "value": s["previous_avg"],
                                "unit": "TL",
                            },
                            {
                                "metric": "bu_ay",
                                "value": s["current"],
                                "unit": "TL",
                            },
                        ],
                        "actions": [],
                    }
                )

        # Recurring payments
        recurring = patterns.get("recurring_payments")
        if recurring and recurring.get("items"):
            cards.append(
                {
                    "id": InsightBuilder._next_id("recur"),
                    "type": "merchant_analysis",
                    "priority": (
                        "MEDIUM" if recurring["total_monthly"] > 500 else "LOW"
                    ),
                    "title": f"Tespit edilen {len(recurring['items'])} tekrarlayan ödeme",
                    "summary": (
                        f"Toplam aylık: {recurring['total_monthly']:.0f} TL, "
                        f"yıllık: {recurring['total_yearly']:.0f} TL."
                    ),
                    "confidence": calc_confidence(15, 0.6),
                    "evidence": [
                        {
                            "metric": "aylik_toplam",
                            "value": recurring["total_monthly"],
                            "unit": "TL",
                        },
                        {
                            "metric": "yillik_toplam",
                            "value": recurring["total_yearly"],
                            "unit": "TL",
                        },
                    ],
                    "actions": [],
                }
            )

        return cards

    # ── Budget Alerts → Cards ─────────────────────────────────────

    @staticmethod
    def from_budget_alerts(budgets: list) -> list:
        """Bütçe aşımları için uyarı kartları üretir."""
        if not budgets:
            return []
        cards = []
        for b in budgets:
            pct = sf(b.get("pct"))
            if pct >= 80:
                status = "aşıldı" if pct >= 100 else "sınıra yaklaştı"
                cards.append(
                    {
                        "id": InsightBuilder._next_id("budget"),
                        "type": "budget_forecast",
                        "priority": "HIGH" if pct >= 100 else "MEDIUM",
                        "title": f"{b.get('category', '?')} bütçesi {status}",
                        "summary": f"{b.get('spent', 0):.0f} TL / {b.get('limit', 0):.0f} TL (%{pct:.0f}).",
                        "confidence": 95,
                        "evidence": [
                            {
                                "metric": "butce",
                                "value": b.get("limit", 0),
                                "unit": "TL",
                            },
                            {
                                "metric": "harcanan",
                                "value": b.get("spent", 0),
                                "unit": "TL",
                            },
                        ],
                        "actions": [],
                    }
                )
        return cards

    # ── Financial Health → Cards ──────────────────────────────────

    @staticmethod
    def from_financial_health(financial_health: dict, goals: list) -> list:
        """Gelir-gider dengesi ve hedef ilerleme bilgilerini insight'a çevirir."""
        cards = []
        fh = financial_health or {}

        period_income = sf(fh.get("period_income"))
        period_spent = sf(fh.get("period_spent"))
        period_net = sf(fh.get("period_net"))
        savings_rate = sf(fh.get("savings_rate"))

        if period_income > 0:
            if savings_rate < 10:
                cards.append(
                    {
                        "id": InsightBuilder._next_id("health"),
                        "type": "financial_health",
                        "priority": "HIGH",
                        "title": "Tasarruf oranı kritik seviyede",
                        "summary": (
                            f"Ay içinde {period_income:.0f} TL gelire karşı "
                            f"{period_spent:.0f} TL harcama var. "
                            f"Tasarruf oranı %{savings_rate:.1f}."
                        ),
                        "confidence": 92,
                        "evidence": [
                            {"metric": "gelir", "value": period_income, "unit": "TL"},
                            {"metric": "gider", "value": period_spent, "unit": "TL"},
                            {
                                "metric": "tasarruf_oranı",
                                "value": savings_rate,
                                "unit": "%",
                            },
                        ],
                        "actions": [
                            "Bu ay en yüksek kategoriye %10 harcama limiti koy.",
                            "Abonelikleri kontrol edip en az birini durdur.",
                        ],
                    }
                )
            elif savings_rate < 15:
                cards.append(
                    {
                        "id": InsightBuilder._next_id("health"),
                        "type": "financial_health",
                        "priority": "MEDIUM",
                        "title": "Tasarruf oranı iyileştirilebilir",
                        "summary": (
                            f"Tasarruf oranınız %{savings_rate:.1f}. "
                            "İdeal seviye olan %20'ye ulaşmak için harcamalarınızı gözden geçirin."
                        ),
                        "confidence": 85,
                        "evidence": [
                            {"metric": "gelir", "value": period_income, "unit": "TL"},
                            {"metric": "gider", "value": period_spent, "unit": "TL"},
                            {
                                "metric": "tasarruf_oranı",
                                "value": savings_rate,
                                "unit": "%",
                            },
                        ],
                        "actions": [
                            "En yüksek harcama kategorisinde %10 azaltmayı dene.",
                            "Tasarruf hedefi oluşturup düzenli birikim başlat.",
                        ],
                    }
                )
            else:
                cards.append(
                    {
                        "id": InsightBuilder._next_id("health"),
                        "type": "financial_health",
                        "priority": "LOW",
                        "title": "Gelir-gider dengesi sağlıklı",
                        "summary": (
                            f"Net bakiye {period_net:.0f} TL ve tasarruf oranı "
                            f"%{savings_rate:.1f}. Bu tempo hedef birikim için uygun."
                        ),
                        "confidence": 85,
                        "evidence": [
                            {"metric": "net", "value": period_net, "unit": "TL"},
                            {
                                "metric": "tasarruf_oranı",
                                "value": savings_rate,
                                "unit": "%",
                            },
                        ],
                        "actions": [
                            "Bu dengeyi korumak için sabit giderleri aylık bir kez gözden geçir."
                        ],
                    }
                )

            # Gelir özet kartı
            cards.append(
                {
                    "id": InsightBuilder._next_id("income"),
                    "type": "income_analysis",
                    "priority": "LOW",
                    "title": f"Aylık geliriniz {period_income:,.0f} TL",
                    "summary": (
                        f"Bu ay {period_income:,.0f} TL gelire karşı "
                        f"{period_spent:,.0f} TL harcama gerçekleşti. "
                        f"Net bakiye {period_net:,.0f} TL."
                    ),
                    "confidence": 95,
                    "evidence": [
                        {"metric": "gelir", "value": period_income, "unit": "TL"},
                        {"metric": "gider", "value": period_spent, "unit": "TL"},
                        {"metric": "net", "value": period_net, "unit": "TL"},
                    ],
                    "actions": [
                        "Gelirinizi çeşitlendirmek için ek gelir kaynakları araştırın.",
                        "Düzenli gelirinizi otomatik tasarrufa yönlendirin.",
                    ],
                }
            )

        elif period_spent > 0:
            cards.append(
                {
                    "id": InsightBuilder._next_id("health"),
                    "type": "financial_health",
                    "priority": "MEDIUM",
                    "title": "Gelir bilgisi eksik",
                    "summary": (
                        f"Bu ay {period_spent:.0f} TL harcama tespit edildi ancak "
                        "gelir kaydı bulunamadı. Gelir bilginizi ekleyerek doğru analiz yapılmasını sağlayın."
                    ),
                    "confidence": 90,
                    "evidence": [{"metric": "gider", "value": period_spent, "unit": "TL"}],
                    "actions": [
                        "Gelirlerinizi sisteme ekleyerek tam finansal görünüm elde edin."
                    ],
                }
            )

        # Hedef ilerleme
        active_goals = [
            g
            for g in (goals or [])
            if str(g.get("status", "active")).lower() == "active"
        ]
        if active_goals:
            progress_values = []
            for goal in active_goals:
                target = sf(goal.get("target_amount"))
                current_g = sf(goal.get("current_amount"))
                if target > 0:
                    progress_values.append((current_g / target) * 100)

            if progress_values:
                avg_progress = sum(progress_values) / len(progress_values)
                cards.append(
                    {
                        "id": InsightBuilder._next_id("goal"),
                        "type": "goal_progress",
                        "priority": "MEDIUM" if avg_progress < 70 else "LOW",
                        "title": f"Hedef ilerleme ortalaması %{avg_progress:.0f}",
                        "summary": (
                            f"{len(active_goals)} aktif hedef var. "
                            f"Ortalama ilerleme %{avg_progress:.1f}."
                        ),
                        "confidence": calc_confidence(
                            len(active_goals), min(avg_progress / 100, 1)
                        ),
                        "evidence": [
                            {
                                "metric": "aktif_hedef",
                                "value": len(active_goals),
                                "unit": "adet",
                            },
                            {
                                "metric": "ortalama_ilerleme",
                                "value": round(avg_progress, 1),
                                "unit": "%",
                            },
                        ],
                        "actions": [
                            "Her hedef için haftalık ara kilometre taşı belirle.",
                            "Tamamlanan hedefleri kapatıp yenisini oluştur.",
                        ],
                    }
                )

        return cards
