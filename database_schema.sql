    CREATE EXTENSION IF NOT EXISTS pgcrypto;

    -- ==========================================
    -- User Data & Auth
    -- ==========================================
    CREATE TABLE IF NOT EXISTS user_data (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        cognito_sub VARCHAR(255) UNIQUE NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        full_name VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS refresh_tokens (
        id SERIAL PRIMARY KEY,
        user_id UUID REFERENCES user_data(id) ON DELETE CASCADE,
        token_hash VARCHAR(255) NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- ==========================================
    -- Receipts (Fişler)
    -- ==========================================
    CREATE TABLE IF NOT EXISTS receipts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES user_data(id) ON DELETE CASCADE,
        
        -- Dosya Bilgileri
        file_url TEXT NOT NULL,
        status VARCHAR(50) DEFAULT 'pending', -- pending, processing, completed, failed
        
        -- OCR ile Doldurulacak Alanlar
        merchant_name VARCHAR(255),
        receipt_date DATE,
        total_amount DECIMAL(12, 2) DEFAULT 0.00,
        currency VARCHAR(10) DEFAULT 'TRY',
        tax_amount DECIMAL(12, 2) DEFAULT 0.00,
        
        -- Kategori (1-8 arası ID)
        category_id INTEGER, 
        
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS receipt_items (
        id SERIAL PRIMARY KEY,
        receipt_id UUID REFERENCES receipts(id) ON DELETE CASCADE,
        item_name VARCHAR(255),
        quantity INTEGER DEFAULT 1,
        unit_price DECIMAL(10, 2),
        total_price DECIMAL(10, 2)
    );

    -- ==========================================
    -- Budgets & Subscriptions
    -- ==========================================
    CREATE TABLE IF NOT EXISTS budgets (
        id SERIAL PRIMARY KEY,
        user_id UUID REFERENCES user_data(id) ON DELETE CASCADE,
        category_name VARCHAR(100) NOT NULL,
        user_id UUID REFERENCES user_data(id) ON DELETE CASCADE,
        
        insight_type VARCHAR(50) NOT NULL, -- spending_summary, warning, advice, __meta__
        insight_text JSONB NOT NULL,       -- Structured JSON data
        priority VARCHAR(20) DEFAULT 'MEDIUM',
        
        related_period VARCHAR(7), -- YYYY-MM
        is_active BOOLEAN DEFAULT TRUE, -- History tutmak için
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- İndeksler (Performans için)
    CREATE INDEX IF NOT EXISTS idx_receipts_user_date ON receipts(user_id, receipt_date);
    CREATE INDEX IF NOT EXISTS idx_insights_user_period ON ai_insights(user_id, related_period);
    CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);
