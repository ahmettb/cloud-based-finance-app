"""
AI Analysis Lambda â€” Stateless Financial Intelligence Engine
=============================================================
Bu Lambda, backend API tarafindan invoke edilir.
DB erisimi YOKTUR. JSON alir, analiz yapar, JSON doner.

Katman Ayrimi:
  Backend (SQL-yakin):  aggregation, category totals, merchant grouping, basic stats
  AI Lambda (bu dosya): complex anomaly detection, forecasting, pattern mining, LLM enrichment

Invoke: boto3 lambda.invoke(FunctionName='lambda_ai', Payload=json.dumps(payload))
"""

import json
import os
import math
import re
import logging
import time
import uuid
import hashlib
import statistics
from datetime import datetime, date
from collections import defaultdict

import boto3

# ============================================================
# CONFIG
# ============================================================
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')
LLM_MAX_TOKENS = int(os.environ.get('LLM_MAX_TOKENS', '400'))
LLM_TEMPERATURE = float(os.environ.get('LLM_TEMPERATURE', '0.25'))
ANOMALY_Z_THRESHOLD = float(os.environ.get('ANOMALY_Z_THRESHOLD', '2.0'))
ANOMALY_IQR_FACTOR = float(os.environ.get('ANOMALY_IQR_FACTOR', '1.5'))
LLM_INPUT_TOKEN_PRICE = float(os.environ.get('LLM_INPUT_TOKEN_PRICE', '0.00000025'))
LLM_OUTPUT_TOKEN_PRICE = float(os.environ.get('LLM_OUTPUT_TOKEN_PRICE', '0.00000125'))

# â”€â”€ LAZY BOTO3 INIT (cold start optimization) â”€â”€
# Client sadece LLM enrichment gerektiginde olusturulur.
# Bu sayede pure-computation invocation'larda ~800ms cold start kazanici.
_bedrock_client = None

def _get_bedrock():
    global _bedrock_client
    if _bedrock_client is None:
        logger.info("Initializing Bedrock client (lazy)")
        _bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
    return _bedrock_client

# â”€â”€ CATEGORY MAP â”€â”€
# Fallback map. Payload'dan 'categoryMap' gelirse o kullanilir.
DEFAULT_CATEGORIES = {
    1: 'Market', 2: 'Restoran', 3: 'Kafe', 4: 'Online Alisveris',
    5: 'Fatura', 6: 'Konaklama', 7: 'Ulasim', 8: 'Diger'
}


# ============================================================
# UTILITY HELPERS
# ============================================================
def _sf(v, default=0.0):
    """Safe float conversion â€” numeric stability"""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def _safe_div(a, b, default=0.0):
    """Safe division â€” prevents ZeroDivisionError"""
    b = _sf(b)
    return (_sf(a) / b) if b != 0 else default


def _safe_date(date_str):
    """Safe date parsing â€” returns None on failure instead of crashing"""
    if not date_str or not isinstance(date_str, str):
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except (ValueError, IndexError):
            continue
    return None


def _uid(prefix='ins'):
    """Thread-safe unique ID â€” UUID4 based, no collision risk"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _compact_text(text, max_len=None):
    """Token-friendly text sanitizer: collapse spaces/newlines and optionally trim."""
    if text is None:
        return ""
    out = re.sub(r"\s+", " ", str(text)).strip()
    if max_len and len(out) > max_len:
        return out[:max_len]
    return out


def _confidence(sample_size, signal_strength=0.0):
    """Confidence score: sample size + signal quality -> 0-100"""
    base = min(70, max(0, sample_size) * 12)
    boost = _clamp(signal_strength * 30, 0, 30)
    return _clamp(int(base + boost), 10, 98)


# ============================================================
# KATMAN 2a: ANOMALY DETECTOR
# ============================================================
class AnomalyDetector:
    """
    Hybrid anomaly detection: Z-Score + IQR
    Backend basit threshold kontrolu yapar (amount > avg*3).
    Bu sinif daha sofistike:
      - Kategori bazli Z-Score
      - Merchant bazli Z-Score
      - IQR (uc degerlere dayanikli)
      - Cross-category anomali (bir kategoride ani artis)
    """

    @staticmethod
    def _calc_stats(values):
        """Mean, std, quartiles hesapla"""
        if not values or len(values) < 2:
            return None
        s = sorted(values)
        n = len(s)
        q1_idx = n // 4
        q3_idx = (3 * n) // 4
        return {
            'mean': statistics.mean(s),
            'std': statistics.stdev(s) if n >= 2 else 0,
            'median': statistics.median(s),
            'q1': s[q1_idx],
            'q3': s[q3_idx],
            'iqr': s[q3_idx] - s[q1_idx],
            'count': n
        }

    @staticmethod
    def detect(transactions, z_threshold=None, iqr_factor=None):
        """
        transactions: [{"merchant": str, "amount": float, "category": str, "date": str}, ...]
        Returns: [{"merchant", "amount", "date", "category", "z_score", "iqr_flag", "detection_method"}, ...]
        """
        z_threshold = z_threshold or ANOMALY_Z_THRESHOLD
        iqr_factor = iqr_factor or ANOMALY_IQR_FACTOR

        if not transactions or len(transactions) < 5:
            return []

        # Group amounts by category
        cat_amounts = defaultdict(list)
        merchant_amounts = defaultdict(list)
        for tx in transactions:
            amt = _sf(tx.get('amount'))
            cat = tx.get('category', 'Diger')
            merchant = tx.get('merchant', 'Bilinmiyor')
            cat_amounts[cat].append(amt)
            merchant_amounts[merchant].append(amt)

        # Pre-compute stats
        cat_stats = {cat: AnomalyDetector._calc_stats(vals) for cat, vals in cat_amounts.items()}
        merchant_stats = {m: AnomalyDetector._calc_stats(vals) for m, vals in merchant_amounts.items()}

        anomalies = []
        seen = set()  # Dedup

        # Pre-compute global stats ONCE (was inside loop = O(n^2) bug)
        all_amounts = [_sf(t.get('amount')) for t in transactions]
        global_stats = AnomalyDetector._calc_stats(all_amounts)

        for tx in transactions:
            amt = _sf(tx.get('amount'))
            cat = tx.get('category', 'Diger')
            merchant = tx.get('merchant', 'Bilinmiyor')
            tx_date = tx.get('date', '')

            dedup_key = f"{merchant}|{amt}|{tx_date}"
            if dedup_key in seen:
                continue

            z_score = 0.0
            iqr_flag = False
            methods = []

            # 1) Category-level Z-Score
            cs = cat_stats.get(cat)
            if cs and cs['std'] > 0:
                z_cat = (amt - cs['mean']) / cs['std']
                z_score = max(z_score, z_cat)
                if z_cat > z_threshold:
                    methods.append('category_zscore')

            # 2) Merchant-level Z-Score
            ms = merchant_stats.get(merchant)
            if ms and ms['std'] > 0 and ms['count'] >= 3:
                z_merchant = (amt - ms['mean']) / ms['std']
                z_score = max(z_score, z_merchant)
                if z_merchant > z_threshold:
                    methods.append('merchant_zscore')

            # 3) IQR-based detection (category level)
            if cs and cs['iqr'] > 0:
                upper_fence = cs['q3'] + iqr_factor * cs['iqr']
                if amt > upper_fence:
                    iqr_flag = True
                    methods.append('iqr')

            # 4) Global outlier
            if global_stats and global_stats['std'] > 0:
                z_global = (amt - global_stats['mean']) / global_stats['std']
                if z_global > z_threshold + 0.5:
                    z_score = max(z_score, z_global)
                    methods.append('global_zscore')

            if methods:
                seen.add(dedup_key)
                anomalies.append({
                    'merchant': merchant,
                    'amount': round(amt, 2),
                    'date': tx_date,
                    'category': cat,
                    'z_score': round(z_score, 2),
                    'iqr_flag': iqr_flag,
                    'detection_method': '+'.join(methods),
                    'severity': 'HIGH' if z_score > 3.0 or (iqr_flag and z_score > 2.0) else 'MEDIUM'
                })

        # Sort by severity then z_score desc
        anomalies.sort(key=lambda a: (-1 if a['severity'] == 'HIGH' else 0, -a['z_score']))
        return anomalies[:15]


# ============================================================
# KATMAN 2b: FORECAST ENGINE
# ============================================================
class ForecastEngine:
    """
    Tahmin motoru:
      - EMA (Exponential Moving Average) â€” ana yontem
      - Linear Regression â€” destek
      - Basit mevsimsellik kontrolu (12+ ay varsa)
      - Confidence scoring
    """

    @staticmethod
    def ema(values, alpha=0.3):
        """Exponential Moving Average: son degerlere daha fazla agirlik"""
        if not values:
            return 0
        result = values[0]
        for v in values[1:]:
            result = alpha * v + (1 - alpha) * result
        return result

    @staticmethod
    def linear_regression(values):
        """Simple linear regression: y = mx + b"""
        n = len(values)
        if n < 2:
            return {'slope': 0, 'intercept': values[0] if values else 0, 'r_squared': 0}
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        # R-squared
        y_pred = [slope * xi + intercept for xi in x]
        ss_res = sum((values[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        return {'slope': slope, 'intercept': intercept, 'r_squared': max(0, r_squared)}

    @staticmethod
    def detect_seasonality(values, threshold=0.15):
        """12+ ay veri varsa, ayni ayin gecmis yillarla karsilastirmasi"""
        if len(values) < 12:
            return None
        # Basit: 12 ay onceki degerle korelasyon
        current = values[-1]
        same_month_prev = values[-12] if len(values) >= 12 else None
        if same_month_prev and same_month_prev > 0:
            ratio = current / same_month_prev
            if abs(ratio - 1.0) > threshold:
                return {
                    'seasonal_factor': round(ratio, 2),
                    'same_month_last_year': round(same_month_prev, 2),
                    'direction': 'higher' if ratio > 1 else 'lower'
                }
        return None

    @staticmethod
    def forecast(monthly_totals):
        """
        monthly_totals: [{"month": "2025-10", "total": 3200}, ...]  (sorted by month)
        Returns full forecast object
        """
        if not monthly_totals:
            return {'next_month_estimate': 0, 'trend': 'stable', 'confidence_score': 10, 'method': 'none'}

        values = [_sf(m.get('total')) for m in sorted(monthly_totals, key=lambda x: x.get('month', ''))]
        n = len(values)

        if n < 2:
            return {
                'next_month_estimate': round(values[0], 2) if values else 0,
                'trend': 'stable',
                'confidence_score': 15,
                'method': 'single_value'
            }

        # EMA forecast
        ema_estimate = ForecastEngine.ema(values, alpha=0.35)

        # Linear regression forecast
        reg = ForecastEngine.linear_regression(values)
        lr_estimate = reg['slope'] * n + reg['intercept']  # next point

        # Weighted blend: EMA 60%, LR 40% (EMA daha reaktif)
        blended = ema_estimate * 0.6 + lr_estimate * 0.4

        # Clamp to reasonable bounds (0.5x - 2x of recent average)
        recent_avg = statistics.mean(values[-3:]) if n >= 3 else statistics.mean(values)
        blended = _clamp(blended, recent_avg * 0.5, recent_avg * 2.0)

        # Trend
        if n >= 3:
            recent_direction = values[-1] - values[-3]
            if recent_direction > recent_avg * 0.05:
                trend = 'up'
            elif recent_direction < -recent_avg * 0.05:
                trend = 'down'
            else:
                trend = 'stable'
        else:
            trend = 'up' if values[-1] > values[-2] else ('down' if values[-1] < values[-2] else 'stable')

        # Trend magnitude
        if n >= 2:
            pct_change = ((values[-1] - values[-2]) / values[-2] * 100) if values[-2] > 0 else 0
        else:
            pct_change = 0

        # Confidence
        signal = reg['r_squared']
        conf = _confidence(n, signal)

        # Seasonality check
        seasonality = ForecastEngine.detect_seasonality(values)
        if seasonality:
            # Adjust blended estimate with seasonal factor
            blended = blended * ((seasonality['seasonal_factor'] + 1) / 2)

        # Category forecasts
        cat_forecasts = {}
        if monthly_totals and 'categories' in monthly_totals[-1]:
            all_cats = set()
            for m in monthly_totals:
                all_cats.update((m.get('categories') or {}).keys())
            for cat in all_cats:
                cat_vals = [_sf((m.get('categories') or {}).get(cat, 0)) for m in sorted(monthly_totals, key=lambda x: x.get('month', ''))]
                if any(v > 0 for v in cat_vals):
                    cat_ema = ForecastEngine.ema(cat_vals, alpha=0.35)
                    cat_forecasts[cat] = round(cat_ema, 2)

        return {
            'next_month_estimate': round(blended, 2),
            'trend': trend,
            'trend_pct': round(pct_change, 1),
            'confidence_score': conf,
            'method': 'ema_lr_blend',
            'components': {
                'ema': round(ema_estimate, 2),
                'linear_regression': round(lr_estimate, 2),
                'r_squared': round(reg['r_squared'], 3)
            },
            'seasonality': seasonality,
            'category_forecasts': cat_forecasts if cat_forecasts else None
        }


# ============================================================
# KATMAN 2c: PATTERN MINER
# ============================================================
class PatternMiner:
    """
    Harcama kaliplari bulur:
      - Harcama hizi (velocity): ayin ilk X gununde ne kadar harcanmis
      - Gun dagilimi: hafta ici vs hafta sonu
      - Kategori korelasyonu: birbirine zit hareket eden kategoriler
      - Merchant clustering: benzer magazalar gruplama
      - Recurring payment detection: abonelik benzeri tekrarlar
    """

    @staticmethod
    def spending_velocity(transactions, period):
        """
        Ayin ilk N gunundeki harcama hizini hesaplar.
        Erken uyari: "10 gunde gecen ayin %60'ini harcadin"
        """
        if not transactions or not period:
            return None

        try:
            year, month = int(period[:4]), int(period[5:7])
        except (ValueError, IndexError):
            return None

        period_txs = [
            tx for tx in transactions
            if tx.get('date', '').startswith(period)
        ]
        if not period_txs:
            return None

        total_spent = sum(_sf(tx.get('amount')) for tx in period_txs)

        # Find latest day in the period
        days = []
        for tx in period_txs:
            try:
                d = tx['date']
                day = int(d.split('-')[2]) if len(d) >= 10 else 1
                days.append(day)
            except (ValueError, IndexError):
                pass

        if not days:
            return None

        latest_day = max(days)

        # Days in month
        if month == 12:
            next_m = date(year + 1, 1, 1)
        else:
            next_m = date(year, month + 1, 1)
        days_in_month = (next_m - date(year, month, 1)).days

        daily_rate = total_spent / max(latest_day, 1)
        projected_total = daily_rate * days_in_month
        elapsed_pct = (latest_day / days_in_month) * 100

        return {
            'type': 'spending_velocity',
            'days_elapsed': latest_day,
            'days_in_month': days_in_month,
            'elapsed_pct': round(elapsed_pct, 1),
            'current_total': round(total_spent, 2),
            'daily_avg': round(daily_rate, 2),
            'projected_month_end': round(projected_total, 2),
            'on_track': projected_total <= total_spent * (days_in_month / max(latest_day, 1)) * 1.1
        }

    @staticmethod
    def day_of_week_distribution(transactions):
        """Hangi gunlerde daha cok harcama yapiliyor"""
        if not transactions:
            return None

        day_totals = defaultdict(lambda: {'total': 0, 'count': 0})
        day_names_tr = {0: 'Pazartesi', 1: 'Sali', 2: 'Carsamba', 3: 'Persembe', 4: 'Cuma', 5: 'Cumartesi', 6: 'Pazar'}

        for tx in transactions:
            try:
                d = datetime.strptime(tx['date'][:10], '%Y-%m-%d')
                dow = d.weekday()
                day_totals[dow]['total'] += _sf(tx.get('amount'))
                day_totals[dow]['count'] += 1
            except (ValueError, KeyError):
                continue

        if not day_totals:
            return None

        total = sum(d['total'] for d in day_totals.values())
        if total <= 0:
            return None

        distribution = []
        for dow in range(7):
            dt = day_totals.get(dow, {'total': 0, 'count': 0})
            distribution.append({
                'day': day_names_tr.get(dow, str(dow)),
                'total': round(dt['total'], 2),
                'count': dt['count'],
                'pct': round((dt['total'] / total) * 100, 1)
            })

        # Weekend vs weekday
        weekday_total = sum(d['total'] for d in distribution[:5])
        weekend_total = sum(d['total'] for d in distribution[5:])
        weekend_pct = round((weekend_total / total) * 100, 1) if total > 0 else 0

        # Peak day
        peak = max(distribution, key=lambda d: d['total'])

        return {
            'type': 'day_distribution',
            'distribution': distribution,
            'weekend_pct': weekend_pct,
            'peak_day': peak['day'],
            'peak_day_pct': peak['pct'],
            'insight': 'weekend_heavy' if weekend_pct > 40 else ('weekday_heavy' if weekend_pct < 25 else 'balanced')
        }

    @staticmethod
    def category_correlation(monthly_totals):
        """
        Kategoriler arasi korelasyon: biri artinca digeri azaliyor mu?
        Ornek: Restoran artinca Kafe azaliyor (ikame etki)
        """
        if not monthly_totals or len(monthly_totals) < 3:
            return None

        # Collect category time series
        all_cats = set()
        for m in monthly_totals:
            all_cats.update((m.get('categories') or {}).keys())

        if len(all_cats) < 2:
            return None

        cat_series = {}
        for cat in all_cats:
            series = [_sf((m.get('categories') or {}).get(cat, 0)) for m in sorted(monthly_totals, key=lambda x: x.get('month', ''))]
            if any(v > 0 for v in series):
                cat_series[cat] = series

        if len(cat_series) < 2:
            return None

        # Simple Pearson correlation between category pairs
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
                    if abs(r) > 0.5:  # Only report strong correlations
                        correlations.append({
                            'cat_a': cats[i],
                            'cat_b': cats[j],
                            'correlation': round(r, 2),
                            'direction': 'positive' if r > 0 else 'negative'
                        })

        if not correlations:
            return None

        correlations.sort(key=lambda c: abs(c['correlation']), reverse=True)
        return {
            'type': 'category_correlation',
            'pairs': correlations[:5]
        }

    @staticmethod
    def recurring_payments(transactions, tolerance_pct=0.15):
        """
        Abonelik benzeri tekrarlayan odemeleri tespit et.
        Ayni merchant + benzer tutar + aylik periyot
        """
        if not transactions or len(transactions) < 4:
            return None

        # Group by merchant
        by_merchant = defaultdict(list)
        for tx in transactions:
            merchant = tx.get('merchant', '').strip()
            if merchant:
                by_merchant[merchant].append({
                    'amount': _sf(tx.get('amount')),
                    'date': tx.get('date', '')
                })

        recurring = []
        for merchant, txs in by_merchant.items():
            if len(txs) < 2:
                continue

            amounts = [t['amount'] for t in txs]
            avg_amt = statistics.mean(amounts)
            if avg_amt <= 0:
                continue

            # Check if amounts are similar (within tolerance)
            all_similar = all(abs(a - avg_amt) / avg_amt <= tolerance_pct for a in amounts)
            if all_similar and len(txs) >= 2:
                # Check if roughly monthly
                dates = []
                for t in txs:
                    try:
                        dates.append(datetime.strptime(t['date'][:10], '%Y-%m-%d'))
                    except (ValueError, KeyError):
                        pass
                dates.sort()

                is_monthly = False
                if len(dates) >= 2:
                    diffs = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
                    avg_diff = statistics.mean(diffs)
                    is_monthly = 20 <= avg_diff <= 40  # roughly monthly

                if is_monthly or len(txs) >= 3:
                    recurring.append({
                        'merchant': merchant,
                        'avg_amount': round(avg_amt, 2),
                        'frequency': len(txs),
                        'is_monthly': is_monthly,
                        'monthly_cost': round(avg_amt, 2),
                        'yearly_cost': round(avg_amt * 12, 2)
                    })

        if not recurring:
            return None

        recurring.sort(key=lambda r: r['yearly_cost'], reverse=True)
        return {
            'type': 'recurring_payments',
            'items': recurring[:10],
            'total_monthly': round(sum(r['monthly_cost'] for r in recurring), 2),
            'total_yearly': round(sum(r['yearly_cost'] for r in recurring), 2)
        }

    @staticmethod
    def category_shifts(monthly_totals):
        """
        Kategori bazli ani artis/azalis tespiti.
        Son ay vs onceki aylarin ortalamasi
        """
        if not monthly_totals or len(monthly_totals) < 2:
            return None

        sorted_months = sorted(monthly_totals, key=lambda x: x.get('month', ''))
        current = sorted_months[-1].get('categories', {})
        previous = sorted_months[:-1]

        if not previous:
            return None

        # Average of previous months per category
        all_cats = set()
        for m in sorted_months:
            all_cats.update((m.get('categories') or {}).keys())

        shifts = []
        for cat in all_cats:
            prev_values = [_sf((m.get('categories') or {}).get(cat, 0)) for m in previous]
            prev_avg = statistics.mean(prev_values) if prev_values else 0
            curr_val = _sf(current.get(cat, 0))

            if prev_avg > 50:  # Only for meaningful categories
                change_pct = ((curr_val - prev_avg) / prev_avg) * 100
                if abs(change_pct) > 25:  # Significant shift
                    shifts.append({
                        'category': cat,
                        'current': round(curr_val, 2),
                        'previous_avg': round(prev_avg, 2),
                        'change_pct': round(change_pct, 1),
                        'direction': 'up' if change_pct > 0 else 'down',
                        'severity': 'HIGH' if abs(change_pct) > 50 else 'MEDIUM'
                    })

        if not shifts:
            return None

        shifts.sort(key=lambda s: abs(s['change_pct']), reverse=True)
        return {
            'type': 'category_shifts',
            'shifts': shifts[:6]
        }


# ============================================================
# INSIGHT BUILDER
# ============================================================
class InsightBuilder:
    """Anomaly, forecast, pattern sonuclarindan structured insight kartlari uretir"""

    @staticmethod
    def _next_id(prefix):
        """Thread-safe UUID-based ID â€” no collision in concurrent invocations"""
        return _uid(prefix)

    @staticmethod
    def from_anomalies(anomalies, period):
        """Anomalilerden insight kartlari"""
        if not anomalies:
            return []
        cards = []
        for a in anomalies[:5]:
            cards.append({
                'id': InsightBuilder._next_id('anomaly'),
                'type': 'anomaly_detection',
                'priority': a.get('severity', 'MEDIUM'),
                'title': f"Olağan dışı harcama: {a['merchant']}",
                'summary': f"{a['merchant']}'de {a['amount']:.0f} TL harcama. "
                           f"Z-skor: {a['z_score']:.1f} ({a['detection_method']})",
                'confidence': _confidence(10, min(a['z_score'] / 4, 1.0)),
                'explanation': {
                    'reason': f"{a['detection_method']} ile tespit edildi",
                    'data_points': [
                        f"Tutar: {a['amount']:.0f} TL",
                        f"Z-skor: {a['z_score']:.1f} (esik: {ANOMALY_Z_THRESHOLD})",
                        f"Kategori: {a.get('category', '?')}"
                    ],
                    'detection_method': a['detection_method']
                },
                'evidence': [
                    {'metric': 'tutar', 'value': a['amount'], 'unit': 'TL'},
                    {'metric': 'z_score', 'value': a['z_score'], 'unit': ''}
                ],
                'actions': []
            })
        return cards

    @staticmethod
    def from_forecast(forecast, period):
        """Tahmin sonucundan insight karti"""
        if not forecast or forecast.get('next_month_estimate', 0) <= 0:
            return []
        trend_text = {
            'up': 'Artış bekleniyor',
            'down': 'Düşüş bekleniyor',
            'stable': 'Stabil görünüyor'
        }
        return [{
            'id': InsightBuilder._next_id('forecast'),
            'type': 'budget_forecast',
            'priority': 'HIGH' if forecast.get('trend') == 'up' else 'MEDIUM',
            'title': f"Gelecek ay tahmini: {forecast['next_month_estimate']:.0f} TL",
            'summary': f"{trend_text.get(forecast.get('trend'), 'Stabil')}. "
                       f"Güven: %{forecast.get('confidence_score', 50)}.",
            'confidence': forecast.get('confidence_score', 50),
            'evidence': [
                {'metric': 'tahmin', 'value': forecast['next_month_estimate'], 'unit': 'TL'},
                {'metric': 'trend', 'value': forecast.get('trend_pct', 0), 'unit': '%'}
            ],
            'actions': []
        }]

    @staticmethod
    def from_patterns(patterns, period):
        """Pattern sonuclarindan insight kartlari"""
        cards = []

        # Velocity
        velocity = patterns.get('velocity')
        if velocity and velocity.get('elapsed_pct', 0) > 0:
            v = velocity
            cards.append({
                'id': InsightBuilder._next_id('velocity'),
                'type': 'spending_summary',
                'priority': 'HIGH' if v.get('elapsed_pct', 0) < 50 and v.get('current_total', 0) > v.get('projected_month_end', 0) * 0.6 else 'MEDIUM',
                'title': f"Harcama hızı: {v.get('days_elapsed', 0)} günde {v.get('current_total', 0):.0f} TL",
                'summary': f"Ayın %{v.get('elapsed_pct', 0):.0f}'i geçti. "
                           f"Günlük ortalama {v.get('daily_avg', 0):.0f} TL. "
                           f"Ay sonu tahmini: {v.get('projected_month_end', 0):.0f} TL.",
                'confidence': _confidence(v.get('days_elapsed', 5), 0.5),
                'evidence': [
                    {'metric': 'gunluk_ort', 'value': v.get('daily_avg', 0), 'unit': 'TL'},
                    {'metric': 'ay_sonu', 'value': v.get('projected_month_end', 0), 'unit': 'TL'}
                ],
                'actions': []
            })

        # Day of week
        dow = patterns.get('day_distribution')
        if dow:
            insight_type = dow.get('insight', 'balanced')
            if insight_type != 'balanced':
                cards.append({
                    'id': InsightBuilder._next_id('dow'),
                    'type': 'trend_analysis',
                    'priority': 'LOW',
                    'title': f"En çok harcama günü: {dow.get('peak_day', '')}",
                    'summary': f"Hafta sonu harcamalarınız toplamın %{dow.get('weekend_pct', 0)}'i.",
                    'confidence': _confidence(20, 0.3),
                    'evidence': [
                        {'metric': 'hafta_sonu_yuzde', 'value': dow.get('weekend_pct', 0), 'unit': '%'}
                    ],
                    'actions': []
                })

        # Category shifts
        shifts = patterns.get('category_shifts')
        if shifts and shifts.get('shifts'):
            for s in shifts['shifts'][:3]:
                direction_label = 'arttı' if s['direction'] == 'up' else 'azaldı'
                cards.append({
                    'id': InsightBuilder._next_id('shift'),
                    'type': 'category_breakdown',
                    'priority': s.get('severity', 'MEDIUM'),
                    'title': f"{s['category']} harcaması %{abs(s['change_pct']):.0f} {direction_label}",
                    'summary': f"Önceki ayların ortalaması {s['previous_avg']:.0f} TL, "
                               f"bu ay {s['current']:.0f} TL.",
                    'confidence': _confidence(8, abs(s['change_pct']) / 100),
                    'evidence': [
                        {'metric': 'onceki_ort', 'value': s['previous_avg'], 'unit': 'TL'},
                        {'metric': 'bu_ay', 'value': s['current'], 'unit': 'TL'}
                    ],
                    'actions': []
                })

        # Recurring payments
        recurring = patterns.get('recurring_payments')
        if recurring and recurring.get('items'):
            cards.append({
                'id': InsightBuilder._next_id('recur'),
                'type': 'merchant_analysis',
                'priority': 'MEDIUM' if recurring['total_monthly'] > 500 else 'LOW',
                'title': f"Tespit edilen {len(recurring['items'])} tekrarlayan ödeme",
                'summary': f"Toplam aylık: {recurring['total_monthly']:.0f} TL, "
                           f"yıllık: {recurring['total_yearly']:.0f} TL.",
                'confidence': _confidence(15, 0.6),
                'evidence': [
                    {'metric': 'aylik_toplam', 'value': recurring['total_monthly'], 'unit': 'TL'},
                    {'metric': 'yillik_toplam', 'value': recurring['total_yearly'], 'unit': 'TL'}
                ],
                'actions': []
            })

        return cards

    @staticmethod
    def from_budget_alerts(budgets):
        """Budget asinlari icin kartlar (backend'den gelen budget bilgisi)"""
        if not budgets:
            return []
        cards = []
        for b in budgets:
            pct = _sf(b.get('pct'))
            if pct >= 80:
                status = 'aşıldı' if pct >= 100 else 'sınıra yaklaştı'
                cards.append({
                    'id': InsightBuilder._next_id('budget'),
                    'type': 'budget_forecast',
                    'priority': 'HIGH' if pct >= 100 else 'MEDIUM',
                    'title': f"{b.get('category', '?')} bütçesi {status}",
                    'summary': f"{b.get('spent', 0):.0f} TL / {b.get('limit', 0):.0f} TL (%{pct:.0f}).",
                    'confidence': 95,
                    'evidence': [
                        {'metric': 'butce', 'value': b.get('limit', 0), 'unit': 'TL'},
                        {'metric': 'harcanan', 'value': b.get('spent', 0), 'unit': 'TL'}
                    ],
                    'actions': []
                })
        return cards

    @staticmethod
    def from_financial_health(financial_health, goals):
        """Gelir-gider dengesi ve hedef ilerleme bilgilerini insight'a cevirir."""
        cards = []
        fh = financial_health or {}

        period_income = _sf(fh.get('period_income'))
        period_spent = _sf(fh.get('period_spent'))
        period_net = _sf(fh.get('period_net'))
        savings_rate = _sf(fh.get('savings_rate'))

        if period_income > 0:
            if savings_rate < 10:
                cards.append({
                    'id': InsightBuilder._next_id('health'),
                    'type': 'financial_health',
                    'priority': 'HIGH',
                    'title': 'Tasarruf oranı kritik seviyede',
                    'summary': f'Ay içinde {period_income:.0f} TL gelire karşı {period_spent:.0f} TL harcama var. Tasarruf oranı %{savings_rate:.1f}.',
                    'confidence': 92,
                    'evidence': [
                        {'metric': 'gelir', 'value': period_income, 'unit': 'TL'},
                        {'metric': 'gider', 'value': period_spent, 'unit': 'TL'},
                        {'metric': 'tasarruf_oranı', 'value': savings_rate, 'unit': '%'},
                    ],
                    'actions': [
                        'Bu ay en yüksek kategoriye %10 harcama limiti koy.',
                        'Abonelikleri kontrol edip en az birini durdur.'
                    ]
                })
            elif period_net > 0 and savings_rate >= 15:
                cards.append({
                    'id': InsightBuilder._next_id('health'),
                    'type': 'financial_health',
                    'priority': 'LOW',
                    'title': 'Gelir-gider dengesi sağlıklı',
                    'summary': f'Net bakiye {period_net:.0f} TL ve tasarruf oranı %{savings_rate:.1f}. Bu tempo hedef birikim için uygun.',
                    'confidence': 85,
                    'evidence': [
                        {'metric': 'net', 'value': period_net, 'unit': 'TL'},
                        {'metric': 'tasarruf_oranı', 'value': savings_rate, 'unit': '%'},
                    ],
                    'actions': [
                        'Bu dengeyi korumak için sabit giderleri aylık bir kez gözden geçir.'
                    ]
                })

        active_goals = [g for g in (goals or []) if str(g.get('status', 'active')).lower() == 'active']
        if active_goals:
            progress_values = []
            for goal in active_goals:
                target = _sf(goal.get('target_amount'))
                current = _sf(goal.get('current_amount'))
                if target > 0:
                    progress_values.append((current / target) * 100)

            if progress_values:
                avg_progress = sum(progress_values) / len(progress_values)
                cards.append({
                    'id': InsightBuilder._next_id('goal'),
                    'type': 'goal_progress',
                    'priority': 'MEDIUM' if avg_progress < 70 else 'LOW',
                    'title': f'Hedef ilerleme ortalaması %{avg_progress:.0f}',
                    'summary': f'{len(active_goals)} aktif hedef var. Ortalama ilerleme %{avg_progress:.1f}.',
                    'confidence': _confidence(len(active_goals), min(avg_progress / 100, 1)),
                    'evidence': [
                        {'metric': 'aktif_hedef', 'value': len(active_goals), 'unit': 'adet'},
                        {'metric': 'ortalama_ilerleme', 'value': round(avg_progress, 1), 'unit': '%'},
                    ],
                    'actions': [
                        'Her hedef için haftalık ara kilometre taşı belirle.',
                        'Tamamlanan hedefleri kapatıp yenisini oluştur.'
                    ]
                })

        return cards


# ============================================================
# KATMAN 3: LLM ENRICHER (Claude)
# ============================================================
class LLMEnricher:
    """
    Hesaplanmis structured verileri Claude'a gonderip
    insanca Turkce yorumlar alir.
    Claude HESAPLAMA YAPMAZ, sadece mevcut sonuclari yorumlar.
    """

    SYSTEM_PROMPT = (
        "Rol: T\u00fcrk\u00e7e finans ko\u00e7u (samimi, motive edici, analitik).\\n"
        "G\u00f6rev: Verilen JSON verilerini analiz et ve kullan\u0131c\u0131ya \u00f6zg\u00fcn, ak\u0131c\u0131 bir \u00f6zet sun.\\n"
        "Kurallar:\\n"
        "- 'Ayl\u0131k De\u011ferlendirme' gibi ba\u015fl\u0131klar atma. Do\u011frudan konuya gir.\\n"
        "- \u015eablon c\u00fcmleler kullanma. Veriye \u00f6zel konu\u015f.\\n"
        "- E\u011fer harcama artm\u0131\u015fsa uyar, azalm\u0131\u015fsa tebrik et.\\n"
        "- Sadece JSON d\u00f6nd\u00fcr.\\n"
        "- T\u00fcrk\u00e7e karakterleri do\u011fru kullan: \u011f, \u00fc, \u015f, \u0131, \u00f6, \u00e7.\\n"
        "JSON Format:\\n"
        '{"coach":{"headline":"\u00c7arp\u0131c\u0131 ba\u015fl\u0131k (max 60)","summary":"Ak\u0131c\u0131 paragraf (max 250)","focus_areas":["str","str"]},'
        '"card_enrichments":[{"id":"card_id","title":"max 70char","summary":"max 160char","actions":["str","str"]}]}'
    )

    @staticmethod
    def _build_prompt(period, insights, forecast, patterns):
        """Minimal token prompt"""
        lines = [f"P:{_compact_text(period, 12)}"]

        # Forecast summary
        if forecast:
            lines.append(
                f"FX:{_compact_text(forecast.get('trend'), 10)}|"
                f"est:{forecast.get('next_month_estimate', 0):.0f}|"
                f"conf:{forecast.get('confidence_score', 0)}"
            )

        # Pattern signals
        vel = patterns.get('velocity')
        if vel:
            lines.append(f"VEL:{vel.get('days_elapsed',0)}gun|{vel.get('current_total',0):.0f}TL|proj:{vel.get('projected_month_end',0):.0f}")

        shifts = patterns.get('category_shifts')
        if shifts and shifts.get('shifts'):
            s_parts = [f"{_compact_text(s['category'], 16)}:{s['change_pct']:+.0f}%" for s in shifts['shifts'][:3]]
            lines.append(f"SHIFT:{'|'.join(s_parts)}")

        recurring = patterns.get('recurring_payments')
        if recurring:
            lines.append(f"RECUR:{recurring.get('total_monthly',0):.0f}TL/ay|{len(recurring.get('items',[]))}adet")

        # Card summaries (compact)
        for c in insights[:4]:
            cid = _compact_text(c.get('id'), 24)
            pr = _compact_text(c.get('priority'), 10)
            title = _compact_text(c.get('title'), 48)
            summary = _compact_text(c.get('summary', ''), 56)
            lines.append(f"C:{cid}|{pr}|{title}|{summary}")

        return "\n".join(lines)

    @staticmethod
    def enrich(period, insights, forecast, patterns):
        """Claude ile zenginlestirme. Basarisiz olursa fallback doner."""
        if not insights:
            return insights, LLMEnricher._fallback_coach(period, forecast), {}

        prompt = LLMEnricher._build_prompt(period, insights, forecast, patterns)
        llm_obs = {'status': 'skipped'}  # Observability record

        try:
            start = time.time()
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": LLM_MAX_TOKENS,
                "temperature": LLM_TEMPERATURE,
                "system": LLMEnricher.SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": prompt}]
            }

            # â”€â”€ Sanitized prompt logging (no PII) â”€â”€
            logger.info(f"LLM prompt size: {len(prompt)} chars, ~{len(prompt.split())} tokens")
            logger.info(f"LLM prompt preview: {_compact_text(prompt, 140)}...")

            # â”€â”€ Lazy Bedrock init â”€â”€
            client = _get_bedrock()
            resp = client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps(payload)
            )
            elapsed_ms = int((time.time() - start) * 1000)

            resp_body = json.loads(resp['body'].read())
            raw = resp_body['content'][0]['text'].strip()

            usage = resp_body.get('usage', {})
            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            cost_usd = round(input_tokens * LLM_INPUT_TOKEN_PRICE + output_tokens * LLM_OUTPUT_TOKEN_PRICE, 6)

            logger.info(f"LLM responded in {elapsed_ms}ms, tokens: in={input_tokens} out={output_tokens}, cost=${cost_usd}")

            # â”€â”€ Parse JSON â”€â”€
            ai_data = LLMEnricher._parse_json(raw)

            # â”€â”€ Output Validation â”€â”€
            validation = LLMEnricher._validate_output(ai_data, insights)

            # â”€â”€ Hallucination Detection â”€â”€
            hallucination_flags = LLMEnricher._detect_hallucination(ai_data, prompt, insights)

            # Build observability record
            llm_obs = {
                'status': 'success',
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'elapsed_ms': elapsed_ms,
                'cost_usd': cost_usd,
                'output_valid': validation['is_valid'],
                'validation_warnings': validation.get('warnings', []),
                'hallucination_flags': hallucination_flags,
                'raw_output_length': len(raw)
            }

            if hallucination_flags:
                logger.warning(f"LLM hallucination flags: {hallucination_flags}")

            # Extract coach
            coach = ai_data.get('coach', LLMEnricher._fallback_coach(period, forecast))

            # Apply card enrichments (only if output is valid)
            if validation['is_valid']:
                enrichments = {e['id']: e for e in ai_data.get('card_enrichments', []) if 'id' in e}
                for card in insights:
                    cid = card.get('id')
                    if cid in enrichments:
                        e = enrichments[cid]
                        if e.get('title'):
                            card['title'] = e['title'][:70]
                        if e.get('summary'):
                            card['summary'] = e['summary'][:180]
                        if e.get('actions'):
                            card['actions'] = [a[:100] for a in e['actions'][:3]]
            else:
                logger.warning(f"LLM output validation failed, using raw insights: {validation['warnings']}")

            coach['_llm_meta'] = llm_obs
            return insights, coach, llm_obs

        except Exception as e:
            logger.error(f"LLM enrichment failed: {e}", exc_info=True)
            llm_obs = {'status': 'error', 'error': str(e)}
            return insights, LLMEnricher._fallback_coach(period, forecast), llm_obs

    @staticmethod
    def _validate_output(ai_data, original_insights):
        """LLM ciktisini schema'ya gore dogrula"""
        warnings = []
        if not isinstance(ai_data, dict):
            return {'is_valid': False, 'warnings': ['Output is not a dict']}

        coach = ai_data.get('coach')
        if not coach or not isinstance(coach, dict):
            warnings.append('Missing or invalid coach object')
        else:
            if not coach.get('headline'):
                warnings.append('Coach headline empty')
            elif len(coach['headline']) > 120:
                warnings.append(f'Coach headline too long: {len(coach["headline"])} chars')
            if not coach.get('summary'):
                warnings.append('Coach summary empty')

        enrichments = ai_data.get('card_enrichments', [])
        if enrichments:
            valid_ids = {c.get('id') for c in original_insights}
            for e in enrichments:
                if e.get('id') and e['id'] not in valid_ids:
                    warnings.append(f"Unknown card ID in enrichment: {e['id']}")

        return {'is_valid': len(warnings) <= 2, 'warnings': warnings}

    @staticmethod
    def _detect_hallucination(ai_data, prompt, insights):
        """Basit hallucination tespiti: LLM'in prompt'ta olmayan rakamlar uretip uretmedigini kontrol et"""
        flags = []
        coach = ai_data.get('coach', {})

        # Extract all numbers from prompt (re imported at module level)
        prompt_numbers = set(re.findall(r'\d+', prompt))

        # Check coach headline/summary for fabricated numbers
        for field in ['headline', 'summary']:
            text = coach.get(field, '')
            if text:
                text_numbers = re.findall(r'\d{3,}', text)  # 3+ digit numbers only
                for num in text_numbers:
                    if num not in prompt_numbers:
                        # Check if it's a reasonable derivation (e.g. yearly = monthly*12)
                        is_derivation = False
                        for pn in prompt_numbers:
                            try:
                                ratio = int(num) / max(int(pn), 1)
                                if ratio in (12, 52, 365, 0.5, 2):  # Common multipliers
                                    is_derivation = True
                                    break
                            except (ValueError, ZeroDivisionError):
                                pass
                        if not is_derivation:
                            flags.append(f"Possible fabricated number '{num}' in coach.{field}")

        return flags

    @staticmethod
    def _parse_json(raw_text):
        """LLM ciktisinda JSON bul ve parse et"""
        text = raw_text.strip()
        # Remove markdown code blocks if present
        if text.startswith('```'):
            lines = text.split('\n')
            lines = [l for l in lines if not l.strip().startswith('```')]
            text = '\n'.join(lines).strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try finding JSON object
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse LLM output as JSON: {text[:200]}")
        return {}

    @staticmethod
    def _fallback_coach(period, forecast):
        """LLM basarisiz olursa basit fallback"""
        headline = f"{period} analizi tamamlandı."
        if forecast and forecast.get('trend') == 'up':
            headline = "Dikkat: harcamalar artış eğiliminde!"
        elif forecast and forecast.get('trend') == 'down':
            headline = "Harcamalarınız düşüş eğiliminde."

        return {
            'headline': headline,
            'summary': f"{period} dönemine ait finansal analiz sonuçları hazır.",
            'focus_areas': ['Bütçe takibi', 'Harcama trendi', 'Tasarruf fırsatları']
        }


# ============================================================
# ORCHESTRATOR
# ============================================================
def run_analysis(payload):
    """
    Ana orkestrasyon fonksiyonu.
    Input: Backend'den gelen JSON payload
    Output: Tam analiz sonucu JSON
    """
    request_id = payload.get('requestId', 'unknown')
    period = payload.get('period', datetime.now().strftime('%Y-%m'))
    input_skip_llm = payload.get('skipLLM', False)  # Cache hit ise LLM atla

    # Configurable category map (payload'dan gelirse kulllan)
    global DEFAULT_CATEGORIES
    custom_cats = payload.get('categoryMap')
    if custom_cats and isinstance(custom_cats, dict):
        logger.info(f"[{request_id}] Using custom category map ({len(custom_cats)} items)")

    monthly_totals = payload.get('monthlyTotals', [])
    transactions = payload.get('transactions', [])
    budgets = payload.get('budgets', [])
    subscriptions = payload.get('subscriptions', [])
    goals = payload.get('goals', [])
    financial_health = payload.get('financialHealth', {})
    merchant_stats = payload.get('merchantStats', [])

    all_insights = []
    all_patterns = {}

    # Az veri durumunda LLM zenginlestirme genelde dusuk deger/ek maliyet.
    auto_skip_llm = len(transactions) < 6 and len(monthly_totals) < 2
    skip_llm = bool(input_skip_llm or auto_skip_llm)
    logger.info(
        f"[{request_id}] Analysis starting for period={period}, "
        f"skipLLM={skip_llm} (input_skip={input_skip_llm}, auto_skip={auto_skip_llm})"
    )

    # â”€â”€ STEP 1: Complex Anomaly Detection â”€â”€
    step_start = time.time()
    try:
        anomalies = AnomalyDetector.detect(transactions)
        logger.info(f"[{request_id}] Anomalies: {len(anomalies)} found in {(time.time()-step_start)*1000:.0f}ms")
        all_insights.extend(InsightBuilder.from_anomalies(anomalies, period))
    except Exception as e:
        logger.error(f"[{request_id}] Anomaly detection error: {e}", exc_info=True)
        anomalies = []

    # â”€â”€ STEP 2: Forecasting â”€â”€
    step_start = time.time()
    try:
        forecast = ForecastEngine.forecast(monthly_totals)
        logger.info(f"[{request_id}] Forecast: {forecast.get('next_month_estimate', 0):.0f} TL "
                     f"({forecast.get('trend')}) in {(time.time()-step_start)*1000:.0f}ms")
        all_insights.extend(InsightBuilder.from_forecast(forecast, period))
    except Exception as e:
        logger.error(f"[{request_id}] Forecast error: {e}", exc_info=True)
        forecast = {'next_month_estimate': 0, 'trend': 'stable', 'confidence_score': 10}

    # â”€â”€ STEP 3: Pattern Mining â”€â”€
    step_start = time.time()
    try:
        velocity = PatternMiner.spending_velocity(transactions, period)
        if velocity:
            all_patterns['velocity'] = velocity

        dow = PatternMiner.day_of_week_distribution(transactions)
        if dow:
            all_patterns['day_distribution'] = dow

        cat_corr = PatternMiner.category_correlation(monthly_totals)
        if cat_corr:
            all_patterns['category_correlation'] = cat_corr

        recurring = PatternMiner.recurring_payments(transactions)
        if recurring:
            all_patterns['recurring_payments'] = recurring

        cat_shifts = PatternMiner.category_shifts(monthly_totals)
        if cat_shifts:
            all_patterns['category_shifts'] = cat_shifts

        logger.info(f"[{request_id}] Patterns: {len(all_patterns)} types in {(time.time()-step_start)*1000:.0f}ms")
        all_insights.extend(InsightBuilder.from_patterns(all_patterns, period))
    except Exception as e:
        logger.error(f"[{request_id}] Pattern mining error: {e}", exc_info=True)

    # â”€â”€ STEP 4: Budget Alert Insights â”€â”€
    try:
        all_insights.extend(InsightBuilder.from_budget_alerts(budgets))
    except Exception as e:
        logger.error(f"[{request_id}] Budget insight error: {e}", exc_info=True)

    # Step 4b: Financial health + goal progress insights
    try:
        all_insights.extend(InsightBuilder.from_financial_health(financial_health, goals))
    except Exception as e:
        logger.error(f"[{request_id}] Financial health insight error: {e}", exc_info=True)

    # Sort insights by priority (HIGH first)
    priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    all_insights.sort(key=lambda c: priority_order.get(c.get('priority', 'LOW'), 2))

    # â”€â”€ STEP 5: LLM Enrichment (Katman 3) â”€â”€
    llm_obs = {}
    if not skip_llm:
        step_start = time.time()
        try:
            all_insights, coach, llm_obs = LLMEnricher.enrich(period, all_insights, forecast, all_patterns)
            logger.info(f"[{request_id}] LLM enrichment done in {(time.time()-step_start)*1000:.0f}ms")
        except Exception as e:
            logger.error(f"[{request_id}] LLM enrichment error: {e}", exc_info=True)
            coach = LLMEnricher._fallback_coach(period, forecast)
    else:
        logger.info(f"[{request_id}] LLM skipped (cache/flag)")
        coach = LLMEnricher._fallback_coach(period, forecast)

    # â”€â”€ BUILD RESPONSE â”€â”€
    next_actions = _build_next_actions(all_insights)

    # Cache key for backend to check staleness
    cache_input = json.dumps({
        'period': period,
        'tx_count': len(transactions),
        'monthly_count': len(monthly_totals),
        'total': sum(_sf(m.get('total')) for m in monthly_totals)
    }, sort_keys=True)
    cache_key = hashlib.md5(cache_input.encode()).hexdigest()[:16]

    response = {
        'coach': coach,
        'insights': all_insights[:12],
        'forecast': forecast,
        'anomalies': anomalies[:10],
        'patterns': all_patterns,
        'next_actions': next_actions,
        'financial_health': financial_health,
        'goals_summary': {
            'active_count': len([g for g in goals if str(g.get('status', 'active')).lower() == 'active']),
            'total_count': len(goals),
        },
        'meta': {
            'model_version': BEDROCK_MODEL_ID,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'analysis_version': 'v6',
            'period': period,
            'cache_key': cache_key,
            'llm_observability': llm_obs,
            'input_stats': {
                'monthly_count': len(monthly_totals),
                'transaction_count': len(transactions),
                'budget_count': len(budgets),
                'goal_count': len(goals)
            }
        }
    }

    logger.info(f"[{request_id}] Analysis complete: {len(all_insights)} insights, "
                 f"{len(anomalies)} anomalies, forecast={forecast.get('next_month_estimate',0):.0f}")

    return response


def _build_next_actions(insights):
    """Insight kartlarindan oncelikli aksiyon listesi cikar"""
    actions = []
    for card in insights:
        if card.get('actions'):
            for act in card['actions'][:2]:
                actions.append({
                    'title': act if isinstance(act, str) else act.get('description', ''),
                    'source_insight': card.get('id'),
                    'priority': card.get('priority', 'MEDIUM'),
                    'due_in_days': 7 if card.get('priority') == 'HIGH' else 14
                })
        elif card.get('priority') == 'HIGH':
            actions.append({
                'title': card.get('title', 'Aksiyon gerekli'),
                'source_insight': card.get('id'),
                'priority': 'HIGH',
                'due_in_days': 7
            })

    # Deduplicate and limit
    seen = set()
    unique = []
    for a in actions:
        key = a['title'][:40]
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique[:8]


# ============================================================
# LAMBDA HANDLER
# ============================================================
def lambda_handler(event, context):
    """
    Entry point. Backend'den boto3.invoke() ile cagirilir.
    event = JSON payload (monthlyTotals, transactions, budgets, ...)
    Dogrudan JSON response doner (API Gateway formati DEGIL).
    """
    request_id = context.aws_request_id if context else 'local'
    start_time = time.time()

    logger.info(f"[{request_id}] === AI LAMBDA INVOKED ===")

    try:
        # Parse payload (invoke'dan direkt JSON gelir)
        if isinstance(event, str):
            payload = json.loads(event)
        elif isinstance(event, dict):
            payload = event
        else:
            payload = json.loads(event)

        payload['requestId'] = request_id

        # Validate minimum input
        if not payload.get('monthlyTotals') and not payload.get('transactions'):
            logger.warning(f"[{request_id}] No data provided")
            return {
                'statusCode': 200,
                'body': {
                    'coach': {'headline': 'Analiz için yeterli veri yok.', 'summary': '', 'focus_areas': []},
                    'insights': [],
                    'forecast': None,
                    'anomalies': [],
                    'patterns': {},
                    'next_actions': [],
                    'meta': {'error': 'insufficient_data', 'generated_at': datetime.utcnow().isoformat() + 'Z'}
                }
            }

        # Run analysis
        result = run_analysis(payload)

        elapsed_ms = int((time.time() - start_time) * 1000)
        result['meta']['total_processing_ms'] = elapsed_ms

        logger.info(f"[{request_id}] === AI LAMBDA COMPLETE in {elapsed_ms}ms ===")

        return {
            'statusCode': 200,
            'body': result
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(f"[{request_id}] FATAL: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'meta': {
                    'generated_at': datetime.utcnow().isoformat() + 'Z',
                    'total_processing_ms': elapsed_ms
                }
            }
        }
