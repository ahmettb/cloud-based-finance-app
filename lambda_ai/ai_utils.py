"""
ai_utils.py — AI Lambda Utility Helpers
========================================
Tüm AI modülleri tarafından kullanılan saf fonksiyonlar.
Dış bağımlılık yok — yalnızca stdlib.
"""

import math
import re
import statistics
import uuid
from datetime import datetime


# ══════════════════════════════════════════════════════════════════
#  Numeric Utilities
# ══════════════════════════════════════════════════════════════════

def sf(v, default: float = 0.0) -> float:
    """Safe float: NaN/Inf → default."""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def safe_div(a, b, default: float = 0.0) -> float:
    """Safe division — ZeroDivisionError'ı önler."""
    b = sf(b)
    return (sf(a) / b) if b != 0 else default


def clamp(v, lo, hi):
    """Değeri [lo, hi] aralığında tutar."""
    return max(lo, min(hi, v))


# ══════════════════════════════════════════════════════════════════
#  String Utilities
# ══════════════════════════════════════════════════════════════════

def compact_text(text, max_len: int | None = None) -> str:
    """Token-dostu metin temizleyici: boşluk/satır sıkıştır, opsiyonel kırp."""
    if text is None:
        return ""
    out = re.sub(r"\s+", " ", str(text)).strip()
    if max_len and len(out) > max_len:
        return out[:max_len]
    return out


# ══════════════════════════════════════════════════════════════════
#  Date Utilities
# ══════════════════════════════════════════════════════════════════

def safe_date(date_str: str | None) -> datetime | None:
    """Güvenli tarih parse — hata durumunda None döner."""
    if not date_str or not isinstance(date_str, str):
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except (ValueError, IndexError):
            continue
    return None


# ══════════════════════════════════════════════════════════════════
#  ID & Confidence
# ══════════════════════════════════════════════════════════════════

def uid(prefix: str = "ins") -> str:
    """Thread-safe UUID4 tabanlı benzersiz ID."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def confidence(sample_size: int, signal_strength: float = 0.0) -> int:
    """Örnek büyüklüğü + sinyal kalitesine göre güven skoru (0-100)."""
    base = min(70, max(0, sample_size) * 12)
    boost = clamp(signal_strength * 30, 0, 30)
    return clamp(int(base + boost), 10, 98)


# Geriye dönük uyumluluk takma adları (mevcut kod referansları için)
_sf = sf
_safe_div = safe_div
_clamp = clamp
_compact_text = compact_text
_safe_date = safe_date
_uid = uid
_confidence = confidence
