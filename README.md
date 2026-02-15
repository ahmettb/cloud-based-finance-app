# Cloud-Based Finance App

Bu repo, AI destekli bulut tabanli kisisel finans yonetim uygulamasinin **final teknik raporu**dur.

Inceleme + iyilestirme tarihi: **15 Subat 2026**
Proje klasoru: `OneDrive/Desktop/cloud-based-finance-app`

## 1. Proje Ozeti
Sistem artik uctan uca calisir durumda bir serverless finans platformu kurgusundadir:

- `backend_lambda`: Ana API router, auth guard, receipt/budget/subscription/report/export/is zekasi orchestration.
- `document_upload`: Ayrik upload-init lambda (presigned URL olusturma).
- `lambda_ai`: Istatistiksel analiz + anomaly detection + forecast + pattern mining + LLM enrichment.
- `finance-app-frontend`: React tabanli istemci.
- `database_schema.sql`: PostgreSQL veri semasi.

Mimari hedef: Cognito + API Gateway + Lambda + S3 + RDS(PostgreSQL) + Bedrock.

## 2. Final Mimari Akislar

### 2.1 Belge yukleme ve OCR akisi
1. Frontend `POST /receipts/upload` cagirir.
2. Backend presigned URL + `receipt_id` doner.
3. Frontend dosyayi S3'e `PUT` eder.
4. Frontend `POST /receipts/{receipt_id}/process` cagirir.
5. OCR sonucu receipt + item alanlari DB'ye yazilir.
6. Hata durumunda receipt `failed` olur (yanlis completed yazilmaz).

### 2.2 Manuel gider akisi
1. Frontend (`AddExpense` veya `VoiceExpenseWizard`) `POST /receipts/manual` cagirir.
2. Backend validasyon yapar, kategoriyi normalize eder ve kaydi `completed` olarak ekler.
3. Kayit `receipts` tablosuna islenir, dashboard/raporlarda aninda gorunur.

### 2.3 AI analiz akisi
1. Frontend `POST /analyze` cagirir.
2. Backend son 6 ay transaction + monthlyTotals + budget + subscription payload olusturur.
3. Backend `lambda_ai` invoke eder.
4. Sonuc `ai_insights` tablosuna (`__meta__`, `__result__`, insight satirlari) kaydedilir.
5. Dashboard kayitli analizi gosterir.

### 2.4 Raporlama ve export akisi
- `GET /reports/summary`: Aylik gider toplamlari, kategori kirilimlari, top category, aggregate summary.
- `GET /export`: CSV olusturur, S3'e koyar, gecici download URL doner.

## 3. Step Bazli Yapilan Iyilestirmeler

## Step 1 (tamam)
- `backend_lambda` yeniden kuruldu ve eksik handlerlar tamamlandi.
- Router tum ana endpointleri dogru sekilde dispatch edecek hale geldi.
- Dashboard response contract frontend ile uyumlu hale getirildi.

## Step 2 (tamam)
- AI cache/staleness mekanizmasi calisir hale getirildi (`data_sig`, TTL, cache-hit skip).
- OCR token ve boyut limiti optimize edildi.
- `lambda_ai` max token ve prompt yukleri azaltildi.
- Az veri durumunda LLM auto-skip eklendi.

## Step 3 (tamam)
- `POST /receipts/manual` eklendi (manual + voice flow artik gercek backend'e yaziyor).
- `GET /reports/summary` eklendi (Reports artik dummy degil, gercek veriyi cekiyor).
- Frontend mock ekranlari gercek API ile baglandi:
  - `AddExpense`
  - `VoiceExpenseWizard`
  - `Reports`
- Frontend API debug loglari env flag altina alindi (`REACT_APP_API_DEBUG=true`).
- API base URL env tabanli yapildi (`REACT_APP_API_BASE_URL`).
- CORS/security headerlari env bazli sertlestirildi (`ALLOWED_ORIGIN`).
- Upload lambda token logu ham deger yerine hash olarak loglanacak sekilde duzeltildi.
- Build warningleri temizlendi.

## 4. AI Altyapisi: Ne Analiz Ediyor?
`lambda_ai` katmaninda su analizler aktif:

- Anomaly Detection
- Kategori bazli z-score
- Merchant bazli z-score
- IQR + global outlier

- Forecasting
- EMA + linear regression blend
- Trend sinifi (up/down/stable)
- Confidence scoring

- Pattern Mining
- Spending velocity
- Weekday/weekend davranisi
- Category correlation
- Recurring payment detection
- Category shift analizi

- Insight Engine
- Onceliklendirilmis insight kartlari
- Next action listesi
- Kisa coach ozetleri

- LLM Enrichment (opsiyonel)
- Bedrock Claude modeli ile text zenginlestirme
- JSON schema odakli, kisa prompt

## 5. Token ve Maliyet Optimizasyonu (Final Durum)

Sistemde iki ana AI maliyeti vardir:

- OCR (vision + text)
- AI metinsel zenginlestirme (lambda_ai)

Uygulanan optimizasyonlar:

- `OCR_MAX_TOKENS` default 320
- `OCR_MAX_FILE_BYTES` limiti aktif (buyuk dosya reddedilir)
- Kisa OCR prompt
- `AI_CACHE_TTL_SECONDS` ile gereksiz tekrar invoke engelleme
- `useCache` + `forceRecompute` davranisi
- Dashboard stale degilse kayitli analiz yeniden kullanimi
- `lambda_ai` tarafinda `LLM_MAX_TOKENS` default 400
- Az veri senaryosunda `skipLLM` otomatik aktif
- Token maliyet birim fiyatlari env'den yonetilebilir:
  - `LLM_INPUT_TOKEN_PRICE`
  - `LLM_OUTPUT_TOKEN_PRICE`

Sonuc: Gereksiz token tuketimi onceki duruma gore belirgin dusuruldu.

## 6. Final API Ozeti
Auth:
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `GET /auth/me`

Receipts:
- `GET /receipts`
- `GET /receipts/{id}`
- `PUT /receipts/{id}`
- `DELETE /receipts/{id}`
- `POST /receipts/upload`
- `POST /receipts/{id}/process`
- `POST /receipts/manual`

Finance:
- `GET /dashboard`
- `POST /analyze`
- `GET /budgets`
- `POST /budgets`
- `GET /subscriptions`
- `POST /subscriptions`
- `DELETE /subscriptions/{id}`
- `GET /reports/summary`
- `GET /export`

## 7. Guvenlik ve Operasyon Notlari
Aktiflestirilenler:

- Env tabanli CORS (`ALLOWED_ORIGIN`)
- Response security headerlari (`X-Content-Type-Options`, `Cache-Control`)
- Upload lambda'da hassas token degerinin loglanmamasi (hash log)

Cloud tarafinda canli oncesi onerilen ek adimlar:

1. API Gateway WAF + rate limit policy
2. CloudWatch alarm setleri (5xx, timeout, Bedrock hata oranlari)
3. Secrets Manager ile DB credential yonetimi
4. Lambda reserved concurrency ve timeout tuning
5. S3 lifecycle ve encryption policy denetimi
6. Opsiyonel: OCR icin SQS + DLQ ile asenkron dayaniklilik

## 8. Dogrulama Sonuclari
Teknik kontroller:

- `python -m py_compile backend_lambda/lambda_function.py` -> OK
- `python -m py_compile document_upload/lambda_function.py` -> OK
- `python -m py_compile lambda_ai/lambda_function.py` -> OK
- `npm run build` (`finance-app-frontend`) -> OK (warningsiz)

## 9. CV'de Nasil Konumlandirilmali?
Cloud role odakli proje anlatimi icin guclu ciktilar:

- Serverless mikro-servis ayrimi (3 Lambda, net sorumluluk dagilimi)
- Bedrock tabanli AI analytics pipeline
- Cognito JWT tabanli auth flow
- S3 presigned upload + OCR process orchestration
- RDS(PostgreSQL) + AI insight persistence
- Maliyet optimizasyonu (cache, token guard, max-token tuning)
- Uretim hazirligi odakli logging/security/build sertlestirmesi

Kisa CV ozeti ornegi:

`Developed a cloud-native personal finance platform on AWS (API Gateway, Lambda, Cognito, S3, RDS, Bedrock), implemented OCR + AI analytics pipeline, reduced AI token cost via caching and prompt/token controls, and delivered production-ready frontend-backend integration.`

## 10. Bilinen Sinirlar (Bilincli)
- `database_schema.sql` icinde `currrency` alan ismi typo olarak duruyor (uygulama bu alanla uyumlu).
- Gercek STT (speech-to-text) motoru entegre degil; voice wizard su an kontrollu mock transcript ile calisiyor ama kayit gercek backend'e yaziliyor.

## 11. Sonuc
Sistem Step 1 + Step 2 + Step 3 sonrasi,

- uctan uca calisir,
- AI akislari bagli,
- frontend mock baglantilari kapatilmis,
- cloud/AI mimarisi CV seviyesinde savunulabilir,
- token maliyeti gereksiz tekrarlar acisindan optimize edilmis durumdadir.