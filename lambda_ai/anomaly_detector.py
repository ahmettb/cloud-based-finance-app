"""
anomaly_detector.py — Hybrid Anomaly Detection (Z-Score + IQR)
================================================================
Backend basit threshold kontrolü yapar (amount > avg*3).
Bu modül daha sofistike tespitler sunar:
  - Kategori bazlı Z-Score
  - Merchant bazlı Z-Score
  - IQR (uç değerlere dayanıklı)
  - Cross-category anomali (bir kategoride ani artış)
"""

import statistics
from collections import defaultdict

from ai_utils import sf, clamp
from ai_config import ANOMALY_Z_THRESHOLD, ANOMALY_IQR_FACTOR


class AnomalyDetector:
    """
    İki aşamalı anomali tespiti:
      1) İstatistiksel (Z-Score + IQR) → nesnel ölçüm
      2) Sıralama: HIGH severity → z_score desc
    """

    @staticmethod
    def _calc_stats(values: list) -> dict | None:
        """Mean, std, quartile hesapla."""
        if not values or len(values) < 2:
            return None
        s = sorted(values)
        n = len(s)
        q1_idx = n // 4
        q3_idx = (3 * n) // 4
        return {
            "mean": statistics.mean(s),
            "std": statistics.stdev(s) if n >= 2 else 0,
            "median": statistics.median(s),
            "q1": s[q1_idx],
            "q3": s[q3_idx],
            "iqr": s[q3_idx] - s[q1_idx],
            "count": n,
        }

    @staticmethod
    def detect(
        transactions: list,
        z_threshold: float | None = None,
        iqr_factor: float | None = None,
    ) -> list:
        """
        Transactions → anomali listesi.

        Args:
            transactions: [{"merchant", "amount", "category", "date"}, ...]
            z_threshold: Z-Score eşiği (None → env var)
            iqr_factor: IQR çarpanı (None → env var)

        Returns:
            [{"merchant", "amount", "date", "category", "z_score",
              "iqr_flag", "detection_method", "severity"}, ...]
        """
        z_threshold = z_threshold or ANOMALY_Z_THRESHOLD
        iqr_factor = iqr_factor or ANOMALY_IQR_FACTOR

        if not transactions or len(transactions) < 5:
            return []

        # ── Gruplama ──────────────────────────────────────────────
        cat_amounts: dict = defaultdict(list)
        merchant_amounts: dict = defaultdict(list)
        for tx in transactions:
            amt = sf(tx.get("amount"))
            cat = tx.get("category", "Diger")
            merchant = tx.get("merchant", "Bilinmiyor")
            cat_amounts[cat].append(amt)
            merchant_amounts[merchant].append(amt)

        cat_stats = {
            cat: AnomalyDetector._calc_stats(vals)
            for cat, vals in cat_amounts.items()
        }
        merchant_stats = {
            m: AnomalyDetector._calc_stats(vals)
            for m, vals in merchant_amounts.items()
        }

        all_amounts = [sf(t.get("amount")) for t in transactions]
        global_stats = AnomalyDetector._calc_stats(all_amounts)

        anomalies = []
        seen: set = set()

        for tx in transactions:
            amt = sf(tx.get("amount"))
            cat = tx.get("category", "Diger")
            merchant = tx.get("merchant", "Bilinmiyor")
            tx_date = tx.get("date", "")

            dedup_key = f"{merchant}|{amt}|{tx_date}"
            if dedup_key in seen:
                continue

            z_score = 0.0
            iqr_flag = False
            methods: list = []

            # 1) Kategori Z-Score
            cs = cat_stats.get(cat)
            if cs and cs["std"] > 0:
                z_cat = (amt - cs["mean"]) / cs["std"]
                z_score = max(z_score, z_cat)
                if z_cat > z_threshold:
                    methods.append("category_zscore")

            # 2) Merchant Z-Score
            ms = merchant_stats.get(merchant)
            if ms and ms["std"] > 0 and ms["count"] >= 3:
                z_merchant = (amt - ms["mean"]) / ms["std"]
                z_score = max(z_score, z_merchant)
                if z_merchant > z_threshold:
                    methods.append("merchant_zscore")

            # 3) IQR (kategori düzeyinde)
            if cs and cs["iqr"] > 0:
                upper_fence = cs["q3"] + iqr_factor * cs["iqr"]
                if amt > upper_fence:
                    iqr_flag = True
                    methods.append("iqr")

            # 4) Global outlier
            if global_stats and global_stats["std"] > 0:
                z_global = (amt - global_stats["mean"]) / global_stats["std"]
                if z_global > z_threshold + 0.5:
                    z_score = max(z_score, z_global)
                    methods.append("global_zscore")

            if methods:
                seen.add(dedup_key)
                anomalies.append(
                    {
                        "merchant": merchant,
                        "amount": round(amt, 2),
                        "date": tx_date,
                        "category": cat,
                        "z_score": round(z_score, 2),
                        "iqr_flag": iqr_flag,
                        "detection_method": "+".join(methods),
                        "severity": (
                            "HIGH"
                            if z_score > 3.0 or (iqr_flag and z_score > 2.0)
                            else "MEDIUM"
                        ),
                    }
                )

        anomalies.sort(
            key=lambda a: (-1 if a["severity"] == "HIGH" else 0, -a["z_score"])
        )
        return anomalies[:15]
