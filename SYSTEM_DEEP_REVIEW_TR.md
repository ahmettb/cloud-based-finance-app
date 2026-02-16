# Cloud-Based Finance App – AI Odaklı Ürünleştirme ve Geliştirme Raporu

Bu rapor, mevcut kod tabanı (backend lambda, ai lambda, frontend dashboard/reports) incelenerek hazırlanmıştır. Amaç: AI’yi sadece "dashboard’da bir kart" olmaktan çıkarıp, kullanıcıya her sayfada işine yarayan, anlaşılır ve güvenilir bir finans asistanına dönüştürmektir.

---

## 1) Mevcut Durum: AI Sistemi Şu Anda Ne Yapıyor?

### 1.1 AI boru hattı (gerçekte çalışan akış)
1. Kullanıcı `POST /analyze` çağırır.
2. Backend, kullanıcının işlem verilerini ve aylık agregasyonları toplar.
3. Backend, bu payload’ı `lambda_ai` fonksiyonuna invoke eder.
4. `lambda_ai` çıktısı (insights, forecast, anomalies, patterns, coach) backend’e döner.
5. Sonuç `ai_insights` tablosuna cache/meta ile kaydedilir.
6. Dashboard `saved_analysis` üzerinden sonucu gösterir.

### 1.2 AI motorunun analitik katmanları
- **Anomaly Detection:** category z-score, merchant z-score, IQR ve global outlier kombinasyonu.
- **Forecast:** EMA + linear regression blend; trend ve confidence üretimi.
- **Pattern Mining:** harcama hızı, gün dağılımı, recurring payment, category shifts.
- **LLM Enrichment:** kural tabanlı insight’ları insan-diliyle coach/öneri metnine çevirme.

### 1.3 Güçlü taraflar
- AI katmanı DB’den bağımsız ve stateless tasarlanmış (ölçeklenebilirlik için doğru).
- LLM maliyeti için `skipLLM`, token limit ve cache yaklaşımı var.
- Dashboard’da AI sonucu persist edilip tekrar kullanılabiliyor.

---

## 2) Kritik İyileştirme Alanları (Önceliklendirilmiş)

## P0 – Güvenlik ve tutarlılık
1. **JWT doğrulama kapsamı dar:** imza/exp/issuer var; ancak `aud/client_id` ve `token_use` doğrulaması net değil.
2. **Her istekte migration check:** runtime’da `ensure_tables_exist()` çağrısı latency ve operasyonel risk oluşturur.
3. **`/analyze` response contract (güncel):** boş veri senaryosu Step-1 ile tekil contract yapısına çekildi; sonraki adımda frontend contract testleriyle kalıcı güvenceye alınmalı.

## P1 – AI’nin kullanıcıya etkisi
1. AI çıktısı çoğunlukla Dashboard ile sınırlı; kullanıcı davranışını yönlendirecek alanlara dağılmamış.
2. Reports sayfasında halihazırda güçlü aylık metrikler var; AI ile zenginleşirse yüksek değer üretir.
3. Önerilerin “neden bu öneri?” açıklaması (explainability) kullanıcı güveni için yetersiz.

## P2 – Ürün kalitesi
1. Bazı UI alanları statik/placeholder öneriler içeriyor.
2. AI aksiyonları ölçümlenebilir KPI’lara bağlı değil (uygulandı mı, tasarrufa etkisi ne?).

---

## 3) AI Sadece Dashboard’da mı Olmalı? (Cevap: Hayır)

AI’yi modern ve gerçekten faydalı yapmak için **çok noktadan, görev odaklı** kullanım önerisi:

## 3.1 Dashboard (anlık durum merkezi)
Dashboard’da AI şu amaçla kalmalı:
- “Bu ay durumun ne?”
- “Risk var mı?”
- “Bugün ne yapmalıyım?”

**Önerilen AI blokları:**
- Aylık risk skoru (0-100)
- Tahmini ay sonu sapma (bütçeyi aşma olasılığı)
- 3 adet net aksiyon (bugün/hafta)

## 3.2 Reports sayfası (derin aylık değerlendirme merkezi)
Reports, AI için en doğru ikinci ana sayfa. Çünkü kullanıcı burada zaten ay seçip detay analiz ediyor.

### Reports’a eklenmesi gereken AI modülleri
1. **Aylık AI Değerlendirmesi (özet panel)**
   - Bu ayın finansal davranış özeti (2-3 cümle)
   - Geçen aya göre değişim (trend nedeni ile birlikte)

2. **“Ayın En Kritik 3 Harcama Olayı”**
   - En yüksek tekil harcama
   - Anomali kabul edilen işlem(ler)
   - Beklenmedik kategori sıçraması

3. **Ürün/Satıcı Sıklığı Analizi**
   - En sık gidilen merchant’lar
   - "Fiyatı artan tekrar eden alışveriş" uyarısı
   - "Bu satıcıda toplam aylık maliyetin" bilgisi

4. **Aylık Tasarruf Senaryosu (What-if mini simülasyon)**
   - “Haftada 2 dışarıda yemek azaltılırsa: +X TL”
   - “Aboneliklerden 1’i iptal edilirse: +Y TL/ay”

5. **Kategori Bazlı AI Yorumları**
   - Her ana kategoriye 1 satır kısa yorum: "Ulaşım stabil, markette %18 artış"

6. **Explainability (Neden bu öneri?)**
   - Her önerinin altında küçük “neden” etiketi:
     - veri dayanağı (örn. 8 işlem, %23 artış)
     - güven skoru (confidence)

---

## 4) Reports Sayfasında AI’yı Nasıl Kurgulamalısın? (Uygulama Tasarımı)

## 4.1 UX prensibi: “Önce veri, sonra yorum, sonra aksiyon”
Sıra şu olmalı:
1. Metrik ve grafik (ham gerçek)
2. AI yorumu (insight)
3. Tek tık aksiyon (ör. bütçe önerisini uygula)

Bu sıralama, AI’nin “sihirli ama anlaşılmaz” görünmesini engeller.

## 4.2 Önerilen component yapısı
Reports içine aşağıdaki bileşenler eklenebilir:
- `MonthlyAIEvaluationCard`
- `CriticalSpendingEventsCard`
- `MerchantFrequencyInsightsCard`
- `WhatIfSavingsCard`
- `ExplainabilityDrawer`

## 4.3 Önerilen backend endpoint
Mevcut `/reports/detailed?month=YYYY-MM` yanına:
- `GET /reports/ai-summary?month=YYYY-MM`

Örnek response:
```json
{
  "month": "2026-02",
  "risk_score": 74,
  "monthly_summary": "Bu ay market ve restoran harcamalarında artış var.",
  "critical_events": [...],
  "merchant_frequency": [...],
  "what_if": [...],
  "category_comments": [...],
  "meta": {"confidence": 81, "generated_at": "..."}
}
```

## 4.4 Performans ve maliyet
- Bu endpoint için de cache kullan (`month + user_id + data_sig`).
- Veri azsa LLM’i atla; sadece deterministic insight üret.
- Ay değişince precompute (opsiyonel cron/event).

---

## 5) Modern Dünyaya Uygun “Gerçek AI Destekli Sistem” İçin Tasarım İlkeleri

1. **Actionable AI:** her insight bir aksiyona bağlansın.
2. **Transparent AI:** önerinin nedeni ve güven skoru gösterilsin.
3. **Controllable AI:** kullanıcı öneriyi kapatabilsin/geri bildirim verebilsin.
4. **Measured AI:** öneri etkisi ölçülsün (tasarruf, tıklama, uygulama oranı).
5. **Cost-aware AI:** düşük değerli çağrılarda LLM devre dışı kalsın.

---

## 6) CV ve Portföy Etkisini Güçlendirecek AI Özellikleri

1. **Financial Copilot Timeline:** kullanıcıya haftalık görev listesi + otomatik takip.
2. **Goal-driven Planner:** hedef (birikim/borç) bazlı öneri optimizasyonu.
3. **Explainable Insight Engine:** her öneri için feature/dayanak görünürlüğü.
4. **Experiment Framework:** farklı prompt/öneri varyantlarını A/B test.
5. **AI Quality Dashboard:** parse success, acceptance rate, suggestion ROI.

Bu 5 başlık, projeyi “AI var” seviyesinden “AI ürünü yönetiliyor” seviyesine taşır.

---

## 7) 3 Adımlı Sistem İyileştirme + Test Planı (Uçtan Uca)

## Adım 1 — Güvenlik + Sözleşme Stabilizasyonu
### Yapılacaklar
- JWT doğrulamada `aud/client_id/token_use` kontrollerini tamamla.
- Runtime migration check’i kaldır; migration’ı deployment pipeline’a taşı.
- `/analyze` response şemasını tek tipte tut (Step-1 sonrası contract testleriyle koru).

### Test paketi
- Auth contract testleri: geçerli/geçersiz token senaryoları.
- API contract test: `/analyze` boş/verili durumda aynı schema.
- Regression: dashboard render test (saved_analysis null/non-null).

### Başarı kriteri
- Güvenlik açıkları kapanır, API tüketimi stabil hale gelir.

---

## Adım 2 — Reports AI Entegrasyonu (Kullanıcı Değeri)
### Yapılacaklar
- `GET /reports/ai-summary` endpoint’i ekle.
- Reports UI’ya 4 AI kartı ekle:
  - Aylık AI Değerlendirmesi
  - Kritik Harcama Olayları
  - Merchant Sıklığı
  - What-if Tasarruf
- Her öneriye “neden” ve “güven” alanı ekle.

### Test paketi
- Backend unit/integration: AI summary üretimi, cache-hit/cold-hit.
- Frontend component testleri: farklı veri yoğunluklarında kart davranışı.
- E2E: ay seçimi -> AI kartlarının güncellenmesi.

### Başarı kriteri
- Reports sayfası pasif rapordan aktif öneri ekranına dönüşür.

---

## Adım 3 — AI Kalite Döngüsü + Ölçümleme
### Yapılacaklar
- Insight feedback (yararlı/yararsız) mekanizması ekle.
- KPI topla: suggestion acceptance, estimated savings uplift.
- Prompt/version registry + A/B test ekle.

### Test paketi
- Telemetry doğrulama testleri (event schema, metric completeness).
- A/B assignment testleri (deterministik segment dağıtımı).
- Finansal etki testleri (simülasyon sonuçlarının tutarlılığı).

### Başarı kriteri
- AI önerileri ölçülebilir biçimde iyileşir, ürün kararları veriye dayanır.

---

## 8) Sonuç
AI’nin doğru kullanımı için en kritik nokta: **doğru yerde doğru derinlikte sunum**.

- Dashboard = hızlı durum + alarm + kısa aksiyon
- Reports = aylık derin yorum + explainability + what-if + uygulama önerisi

Bu stratejiyle sistem, kullanıcı açısından gerçekten faydalı ve modern; teknik açıdan ise CV’de güçlü ve mülakatta savunulabilir bir “AI-first finance product” haline gelir.
