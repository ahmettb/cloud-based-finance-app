"""
pattern_miner.py — Spending Pattern Analysis
=============================================
Harcama kalıpları çıkarımı:
  - Harcama hızı (velocity): ayın ilk N gününde ne kadar harcanmış
  - Gün dağılımı: hafta içi vs hafta sonu analizi
  - Kategori korelasyonu: birbirine zıt hareket eden kategoriler
  - Tekrarlayan ödeme tespiti: abonelik benzeri işlemler
  - Kategori kaymaları: ani artış/azalış tespiti
"""

import math
import statistics
from collections import defaultdict
from datetime import date, datetime

from ai_utils import sf


class PatternMiner:
    """
    Tüm statik metodlar — state tutulmaz.
    Her metod None veya dict döner; None → veri yetersiz.
    """

    # ── Spending Velocity ──────────────────────────────────────────

    @staticmethod
    def spending_velocity(transactions: list, period: str) -> dict | None:
        """
        Ayın ilk N gününde harcama hızını hesaplar.
        Erken uyarı: '10 günde geçen ayın %60'ını harcadın'

        Args:
            transactions: tüm işlemler listesi
            period: "YYYY-MM"

        Returns:
            velocity dict veya None (yetersiz veri)
        """
        if not transactions or not period:
            return None

        try:
            year, month = int(period[:4]), int(period[5:7])
        except (ValueError, IndexError):
            return None

        period_txs = [
            tx for tx in transactions if tx.get("date", "").startswith(period)
        ]
        if not period_txs:
            return None

        total_spent = sum(sf(tx.get("amount")) for tx in period_txs)
        days = []
        for tx in period_txs:
            try:
                d = tx["date"]
                day_num = int(d.split("-")[2]) if len(d) >= 10 else 1
                days.append(day_num)
            except (ValueError, IndexError):
                pass

        if not days:
            return None

        latest_day = max(days)
        next_m = (
            date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        )
        days_in_month = (next_m - date(year, month, 1)).days
        daily_rate = total_spent / max(latest_day, 1)
        projected_total = daily_rate * days_in_month
        elapsed_pct = (latest_day / days_in_month) * 100

        return {
            "type": "spending_velocity",
            "days_elapsed": latest_day,
            "days_in_month": days_in_month,
            "elapsed_pct": round(elapsed_pct, 1),
            "current_total": round(total_spent, 2),
            "daily_avg": round(daily_rate, 2),
            "projected_month_end": round(projected_total, 2),
            "on_track": projected_total
            <= total_spent * (days_in_month / max(latest_day, 1)) * 1.1,
        }

    # ── Day-of-Week Distribution ───────────────────────────────────

    @staticmethod
    def day_of_week_distribution(transactions: list) -> dict | None:
        """Hangi günlerde daha çok harcama yapılıyor."""
        if not transactions:
            return None

        day_totals: dict = defaultdict(lambda: {"total": 0, "count": 0})
        day_names_tr = {
            0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
            4: "Cuma", 5: "Cumartesi", 6: "Pazar",
        }

        for tx in transactions:
            try:
                d = datetime.strptime(tx["date"][:10], "%Y-%m-%d")
                dow = d.weekday()
                day_totals[dow]["total"] += sf(tx.get("amount"))
                day_totals[dow]["count"] += 1
            except (ValueError, KeyError):
                continue

        if not day_totals:
            return None

        total = sum(d["total"] for d in day_totals.values())
        if total <= 0:
            return None

        distribution = []
        for dow in range(7):
            dt = day_totals.get(dow, {"total": 0, "count": 0})
            distribution.append(
                {
                    "day": day_names_tr.get(dow, str(dow)),
                    "total": round(dt["total"], 2),
                    "count": dt["count"],
                    "pct": round((dt["total"] / total) * 100, 1),
                }
            )

        weekday_total = sum(d["total"] for d in distribution[:5])
        weekend_total = sum(d["total"] for d in distribution[5:])
        weekend_pct = round((weekend_total / total) * 100, 1) if total > 0 else 0
        peak = max(distribution, key=lambda d: d["total"])

        return {
            "type": "day_distribution",
            "distribution": distribution,
            "weekend_pct": weekend_pct,
            "peak_day": peak["day"],
            "peak_day_pct": peak["pct"],
            "insight": (
                "weekend_heavy"
                if weekend_pct > 40
                else ("weekday_heavy" if weekend_pct < 25 else "balanced")
            ),
        }

    # ── Category Correlation ───────────────────────────────────────

    @staticmethod
    def category_correlation(monthly_totals: list) -> dict | None:
        """
        Kategoriler arası korelasyon: biri artınca diğeri azalıyor mu?
        Örnek: Restoran artınca Kafe azalıyor (ikame etkisi).
        """
        if not monthly_totals or len(monthly_totals) < 3:
            return None

        all_cats: set = set()
        for m in monthly_totals:
            all_cats.update((m.get("categories") or {}).keys())

        if len(all_cats) < 2:
            return None

        cat_series: dict = {}
        for cat in all_cats:
            series = [
                sf((m.get("categories") or {}).get(cat, 0))
                for m in sorted(monthly_totals, key=lambda x: x.get("month", ""))
            ]
            if any(v > 0 for v in series):
                cat_series[cat] = series

        if len(cat_series) < 2:
            return None

        correlations = []
        cats = list(cat_series.keys())
        for i in range(len(cats)):
            for j in range(i + 1, len(cats)):
                a = cat_series[cats[i]]
                b = cat_series[cats[j]]
                n = min(len(a), len(b))
                if n < 3:
                    continue
                a, b = a[:n], b[:n]
                a_mean = statistics.mean(a)
                b_mean = statistics.mean(b)
                num = sum((a[k] - a_mean) * (b[k] - b_mean) for k in range(n))
                den_a = math.sqrt(sum((a[k] - a_mean) ** 2 for k in range(n)))
                den_b = math.sqrt(sum((b[k] - b_mean) ** 2 for k in range(n)))
                if den_a > 0 and den_b > 0:
                    r = num / (den_a * den_b)
                    if abs(r) > 0.5:
                        correlations.append(
                            {
                                "cat_a": cats[i],
                                "cat_b": cats[j],
                                "correlation": round(r, 2),
                                "direction": "positive" if r > 0 else "negative",
                            }
                        )

        if not correlations:
            return None

        correlations.sort(key=lambda c: abs(c["correlation"]), reverse=True)
        return {"type": "category_correlation", "pairs": correlations[:5]}

    # ── Recurring Payments ─────────────────────────────────────────

    @staticmethod
    def recurring_payments(
        transactions: list, tolerance_pct: float = 0.15
    ) -> dict | None:
        """
        Abonelik benzeri tekrarlayan ödemeleri tespit et.
        Aynı merchant + benzer tutar + aylık periyot.
        """
        if not transactions or len(transactions) < 4:
            return None

        by_merchant: dict = defaultdict(list)
        for tx in transactions:
            merchant = tx.get("merchant", "").strip()
            if merchant:
                by_merchant[merchant].append(
                    {"amount": sf(tx.get("amount")), "date": tx.get("date", "")}
                )

        recurring = []
        for merchant, txs in by_merchant.items():
            if len(txs) < 2:
                continue
            amounts = [t["amount"] for t in txs]
            avg_amt = statistics.mean(amounts)
            if avg_amt <= 0:
                continue
            all_similar = all(
                abs(a - avg_amt) / avg_amt <= tolerance_pct for a in amounts
            )
            if all_similar and len(txs) >= 2:
                dates = []
                for t in txs:
                    try:
                        dates.append(
                            datetime.strptime(t["date"][:10], "%Y-%m-%d")
                        )
                    except (ValueError, KeyError):
                        pass
                dates.sort()
                is_monthly = False
                if len(dates) >= 2:
                    diffs = [
                        (dates[i + 1] - dates[i]).days
                        for i in range(len(dates) - 1)
                    ]
                    avg_diff = statistics.mean(diffs)
                    is_monthly = 20 <= avg_diff <= 40
                if is_monthly or len(txs) >= 3:
                    recurring.append(
                        {
                            "merchant": merchant,
                            "avg_amount": round(avg_amt, 2),
                            "frequency": len(txs),
                            "is_monthly": is_monthly,
                            "monthly_cost": round(avg_amt, 2),
                            "yearly_cost": round(avg_amt * 12, 2),
                        }
                    )

        if not recurring:
            return None

        recurring.sort(key=lambda r: r["yearly_cost"], reverse=True)
        return {
            "type": "recurring_payments",
            "items": recurring[:10],
            "total_monthly": round(sum(r["monthly_cost"] for r in recurring), 2),
            "total_yearly": round(sum(r["yearly_cost"] for r in recurring), 2),
        }

    # ── Category Shifts ────────────────────────────────────────────

    @staticmethod
    def category_shifts(monthly_totals: list) -> dict | None:
        """
        Kategori bazlı ani artış/azalış tespiti.
        Son ay vs. önceki ayların ortalaması.
        """
        if not monthly_totals or len(monthly_totals) < 2:
            return None

        sorted_months = sorted(monthly_totals, key=lambda x: x.get("month", ""))
        current = sorted_months[-1].get("categories", {})
        previous = sorted_months[:-1]

        if not previous:
            return None

        all_cats: set = set()
        for m in sorted_months:
            all_cats.update((m.get("categories") or {}).keys())

        shifts = []
        for cat in all_cats:
            prev_values = [
                sf((m.get("categories") or {}).get(cat, 0)) for m in previous
            ]
            prev_avg = statistics.mean(prev_values) if prev_values else 0
            curr_val = sf(current.get(cat, 0))
            if prev_avg > 50:
                change_pct = ((curr_val - prev_avg) / prev_avg) * 100
                if abs(change_pct) > 25:
                    shifts.append(
                        {
                            "category": cat,
                            "current": round(curr_val, 2),
                            "previous_avg": round(prev_avg, 2),
                            "change_pct": round(change_pct, 1),
                            "direction": "up" if change_pct > 0 else "down",
                            "severity": (
                                "HIGH" if abs(change_pct) > 50 else "MEDIUM"
                            ),
                        }
                    )

        if not shifts:
            return None

        shifts.sort(key=lambda s: abs(s["change_pct"]), reverse=True)
        return {"type": "category_shifts", "shifts": shifts[:6]}
