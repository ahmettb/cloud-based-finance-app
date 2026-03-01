"""
forecast_engine.py — Time-Series Forecast Engine
=================================================
EMA + Linear Regression karışımıyla bir sonraki ayın harcamasını tahmin eder.
  - EMA (Exponential Moving Average) — ana yöntem: son değerlere daha fazla ağırlık
  - Linear Regression — destek: uzun dönem trendi
  - Mevsimsellik tespiti (12+ ay veri varsa)
  - Confidence scoring
"""

import statistics
from datetime import date

from ai_utils import sf, clamp, confidence as calc_confidence, safe_div


class ForecastEngine:
    """
    Aylık harcama tahmin motoru.
    Girdi: [{month: "YYYY-MM", total: float, categories?: {...}}, ...]
    Çıktı: tam tahmin objesi (next_month_estimate, trend, confidence_score, ...)
    """

    @staticmethod
    def ema(values: list, alpha: float = 0.3) -> float:
        """Üstel Hareketli Ortalama: son değerlere daha fazla ağırlık."""
        if not values:
            return 0.0
        result = values[0]
        for v in values[1:]:
            result = alpha * v + (1 - alpha) * result
        return result

    @staticmethod
    def linear_regression(values: list) -> dict:
        """Basit lineer regresyon: y = mx + b"""
        n = len(values)
        if n < 2:
            return {
                "slope": 0,
                "intercept": values[0] if values else 0,
                "r_squared": 0,
            }
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        y_pred = [slope * xi + intercept for xi in x]
        ss_res = sum((values[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        return {
            "slope": slope,
            "intercept": intercept,
            "r_squared": max(0.0, r_squared),
        }

    @staticmethod
    def detect_seasonality(values: list, threshold: float = 0.15) -> dict | None:
        """12+ ay veri varsa aynı ayın geçen yılla karşılaştırması."""
        if len(values) < 12:
            return None
        current = values[-1]
        same_month_prev = values[-12] if len(values) >= 12 else None
        if same_month_prev and same_month_prev > 0:
            ratio = current / same_month_prev
            if abs(ratio - 1.0) > threshold:
                return {
                    "seasonal_factor": round(ratio, 2),
                    "same_month_last_year": round(same_month_prev, 2),
                    "direction": "higher" if ratio > 1 else "lower",
                }
        return None

    @staticmethod
    def forecast(monthly_totals: list) -> dict:
        """
        Ana tahmin fonksiyonu.

        Args:
            monthly_totals: [{month: "2025-10", total: 3200, categories?: {...}}, ...]
                            (ay sırasına göre sıralı)

        Returns:
            {next_month_estimate, trend, trend_pct, confidence_score, method,
             components, seasonality, category_forecasts}
        """
        if not monthly_totals:
            return {
                "next_month_estimate": 0,
                "trend": "stable",
                "confidence_score": 10,
                "method": "none",
            }

        values = [
            sf(m.get("total"))
            for m in sorted(monthly_totals, key=lambda x: x.get("month", ""))
        ]
        n = len(values)

        if n < 2:
            return {
                "next_month_estimate": round(values[0], 2) if values else 0,
                "trend": "stable",
                "confidence_score": 15,
                "method": "single_value",
            }

        # EMA tahmini
        ema_estimate = ForecastEngine.ema(values, alpha=0.35)

        # LR tahmini
        reg = ForecastEngine.linear_regression(values)
        lr_estimate = reg["slope"] * n + reg["intercept"]  # bir sonraki nokta

        # Ağırlıklı karışım: EMA %60, LR %40
        blended = ema_estimate * 0.6 + lr_estimate * 0.4

        # Makul sınırlar: son ortalamanın 0.5x-2x'i
        recent_avg = (
            statistics.mean(values[-3:]) if n >= 3 else statistics.mean(values)
        )
        blended = clamp(blended, recent_avg * 0.5, recent_avg * 2.0)

        # Trend
        if n >= 3:
            recent_direction = values[-1] - values[-3]
            if recent_direction > recent_avg * 0.05:
                trend = "up"
            elif recent_direction < -recent_avg * 0.05:
                trend = "down"
            else:
                trend = "stable"
        else:
            trend = (
                "up"
                if values[-1] > values[-2]
                else ("down" if values[-1] < values[-2] else "stable")
            )

        pct_change = (
            ((values[-1] - values[-2]) / values[-2] * 100) if values[-2] > 0 else 0
        )

        conf = calc_confidence(n, reg["r_squared"])

        seasonality = ForecastEngine.detect_seasonality(values)
        if seasonality:
            blended = blended * ((seasonality["seasonal_factor"] + 1) / 2)

        # Kategori tahminleri
        cat_forecasts: dict = {}
        if monthly_totals and "categories" in monthly_totals[-1]:
            all_cats: set = set()
            for m in monthly_totals:
                all_cats.update((m.get("categories") or {}).keys())
            for cat in all_cats:
                cat_vals = [
                    sf((m.get("categories") or {}).get(cat, 0))
                    for m in sorted(monthly_totals, key=lambda x: x.get("month", ""))
                ]
                if any(v > 0 for v in cat_vals):
                    cat_forecasts[cat] = round(
                        ForecastEngine.ema(cat_vals, alpha=0.35), 2
                    )

        return {
            "next_month_estimate": round(blended, 2),
            "trend": trend,
            "trend_pct": round(pct_change, 1),
            "confidence_score": conf,
            "method": "ema_lr_blend",
            "components": {
                "ema": round(ema_estimate, 2),
                "linear_regression": round(lr_estimate, 2),
                "r_squared": round(reg["r_squared"], 3),
            },
            "seasonality": seasonality,
            "category_forecasts": cat_forecasts if cat_forecasts else None,
        }
