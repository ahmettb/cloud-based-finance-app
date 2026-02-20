# Finans Uygulaması - Final Sistem Raporu & Özellik Seti

## 1. Giriş ve Vizyon
Bu proje, kullanıcının finansal durumunu **karıştırmadan**, **otomatize ederek** ve **akıllı analizlerle** yönetmesini sağlayan kişisel bir finans asistanıdır.

**Temel Felsefe:**
- **Veri Girişi Minimized:** Fiş tarama (OCR) ve tekrarlayan şablonlarla manuel giriş en aza indirilir.
- **Ayrıştırılmış Yönetim:** "Sabit" (Kira, Fatura) ve "Değişken" (Market, Yemek) giderler asla birbirine karışmaz.
- **Proaktif AI:** Kullanıcı sormadan sistem uyarır ("Bu ay market harcaması %20 arttı").

---

## 2. Sistem Mimarisi ve Kullanıcı Akışları (User Flows)

### A. Modüller ve Özellikler

#### 1. Dashboard (Ana Komuta Merkezi)
*   **Amaç:** Kullanıcının finansal sağlığını tek bakışta görmesi.
*   **Özellikler:**
    *   **Net Bakiye:** (Toplam Gelir - (Sabit Giderler + Değişken Giderler)).
    *   **AI Öngörüsü:** "Ay sonuna kadar tahmini 3.000 TL daha harcayacaksın."
    *   **Acil Durumlar:** Yaklaşan son ödeme tarihleri (Sabit Giderlerden çekilir).
    *   **Hızlı Ekle:** Hızlı fiş yükle veya manuel harcama ekle butonu.

#### 2. Gelir Yönetimi (Incomes)
*   **Amaç:** Nakit girişini takip etmek.
*   **Özellikler:**
    *   Maaş, Prim, Kira Geliri gibi kalemler.
    *   "Düzenli Gelir" seçeneği ile her ay otomatik eklenme.

#### 3. Gider Yönetimi (Expenses) - **(Merkezi Modül)**
Bu modül iki ana sekmeye ayrılır ve sistemin kalbidir.

*   **Tab 1: Sabit Giderler (Fixed Expenses)**
    *   **Tanım:** Tutarı veya tarihi belli olan, her ay ödenmesi zorunlu kalemler.
    *   **Özellikler:**
        *   **Grup Yapısı:** Ev (Kira, Aidat), Dijital (Netflix, Spotify), Kredi (Konut, Taşıt).
        *   **Takip:** "Ödendi/Ödenmedi" işaretleme.
        *   **Geçmiş:** "Geçmiş Ekle" butonu ile unutulan ödemeler girilebilir.
        *   **Otomasyon:** Bir sonraki ay otomatik olarak "Bekliyor" statüsünde yeni kalem oluşturulur.

*   **Tab 2: Düzensiz Giderler (Variable Expenses)**
    *   **Tanım:** Günlük yaşamda yapılan, miktarı değişen harcamalar (Market, Benzin, Yemek).
    *   **Özellikler:**
        *   **Entegrasyon:** "Dokümanlar" sayfasından taranan fişler otomatik buraya düşer.
        *   **Filtreleme:** Ay/Yıl ve Kategori bazlı filtreleme.
        *   **AI Analizi:** Sadece bu sekmeye özel, o ayki harcama alışkanlığını yorumlayan AI kutucuğu (Örn: "Dışarıda yeme-içme bütçeni aşıyorsun").

#### 4. Bütçe Takibi (Budget)
*   **Amaç:** Harcamalara sınır koymak.
*   **Özellikler:**
    *   Kategori bazlı limit belirleme (Örn: Market için 5.000 TL).
    *   **Düzensiz Giderler** ile konuşur; market harcaması yapıldıkça çubuk dolar.
    *   Limit aşımında Dashboard'da uyarı verir.

#### 5. Dokümanlar (Receipts/OCR)
*   **Amaç:** Veri giriş hamallığını bitirmek.
*   **Özellikler:**
    *   Fotoğraf çek/Yükle -> AWS Textract/AI -> JSON Veri.
    *   Onaylandıktan sonra **Düzensiz Giderler** tablosuna otomatik kayıt atar.

#### 6. Raporlar (Reports)
*   **Amaç:** Büyük resmi görmek.
*   **Özellikler:**
    *   Gelir/Gider Pastası.
    *   Aylık Trend Grafiği (Geçen aya göre ne durumdayım?).

---

## 3. Veri Akışı ve Entegrasyon Senaryosu

1.  **Fiş Yükleme:**
    *   Kullanıcı `Dokümanlar` sayfasına fiş yükler.
    *   Backend (OCR) fişi okur: "Migros, 1250 TL, Tarih: 16.02.2026".
    *   Kullanıcı onayıyla bu veri veritabanına `receipts` tablosuna ve eş zamanlı olarak `variable_expenses` (sanal) yapısına işlenir.

2.  **Otomatik Sorgu:**
    *   Kullanıcı `Gider Yönetimi` > `Düzensiz Giderler` sekmesine geldiğinde, sistem hem manuel eklenenleri hem de fişlerden gelenleri tarih sırasına göre listeler.

3.  **Bütçe Kontrolü:**
    *   Sistem, "Market" kategorisindeki toplam harcamayı toplar.
    *   `Bütçe Takibi` sayfasındaki 5.000 TL limitiyle kıyaslar.
    *   %80'e ulaşıldıysa Dashboard'da "Market bütçen dolmak üzere" uyarısı çıkarır.

---

## 4. Finalize Edilmesi Gereken Teknik İşler

1.  **Backend (Lambda):**
    *   `GET /expenses?type=fixed` ve `GET /expenses?type=variable` ayrımını netleştirmek.
    *   OCR servisi çalıştığında veriyi sadece `receipts` tablosuna değil, harcama olarak sorgulanabilir bir view veya yapıya dönüştürmek.
    *   Sabit giderlerin her ayın 1'inde otomatik yenilenmesi için bir *EventBridge Scheduler* kurgusu (veya frontend'de kullanıcının girdiği tarihte kontrol mekanizması).

2.  **Veritabanı (SQL):**
    *   `fixed_expenses` tablosu oluşturulmalı (Şu an mock data kullanıyoruz).
    *   `variable_expenses` tablosu oluşturulmalı (Fişlerle ilişkilendirilmeli).

3.  **Frontend:**
    *   `Expenses.js` içindeki Mock verilerin API'ye bağlanması.
    *   `Dashboard.js`'nin bu yeni yapıdan veri çekmesi.

---

## 5. Özet
Sistem şu an **Frontend** tarafında neredeyse hazır (Mockup verilerle). Yapılması gereken tek şey, bu mantığı **Backend** ve **Veritabanı** tarafında kalıcı hale getirmektir. Kullanıcı deneyimi açısından (UX), "Sabit" ve "Düzensiz" ayrımı kafa karışıklığını tamamen çözecektir.
