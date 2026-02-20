CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ==========================================
-- User Data & Auth
-- ==========================================
CREATE TABLE IF NOT EXISTS user_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cognito_sub VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id, expires_at);

-- ==========================================
-- Receipts
-- ==========================================
CREATE TABLE IF NOT EXISTS receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    file_url TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, processing, completed, failed, deleted
    merchant_name VARCHAR(255),
    receipt_date DATE,
    total_amount DECIMAL(12, 2) DEFAULT 0.00,
    currency VARCHAR(10) DEFAULT 'TRY',
    tax_amount DECIMAL(12, 2) DEFAULT 0.00,
    category_id INTEGER,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipt_items (
    id BIGSERIAL PRIMARY KEY,
    receipt_id UUID NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    item_name VARCHAR(255),
    quantity INTEGER DEFAULT 1,
    unit_price DECIMAL(10, 2),
    total_price DECIMAL(10, 2)
);

CREATE INDEX IF NOT EXISTS idx_receipts_user_date ON receipts(user_id, receipt_date);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);
CREATE INDEX IF NOT EXISTS idx_receipt_items_receipt_id ON receipt_items(receipt_id);

-- ==========================================
-- Planning
-- ==========================================
CREATE TABLE IF NOT EXISTS budgets (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    category_name VARCHAR(100) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, category_name)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    next_payment_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_budgets_user ON budgets(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id, next_payment_date);

-- ==========================================
-- AI Insights
-- ==========================================
CREATE TABLE IF NOT EXISTS ai_insights (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    insight_type VARCHAR(50) NOT NULL, -- spending_summary, warning, advice, __meta__, __result__, __feedback__
    insight_text JSONB NOT NULL,
    priority VARCHAR(20) DEFAULT 'MEDIUM',
    related_period VARCHAR(7), -- YYYY-MM
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_insights_user_period ON ai_insights(user_id, related_period);
CREATE INDEX IF NOT EXISTS idx_insights_type_period ON ai_insights(insight_type, related_period);

-- ==========================================
-- Financial Goals (MVP personalization layer)
-- ==========================================
CREATE TABLE IF NOT EXISTS financial_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    title VARCHAR(120) NOT NULL,
    target_amount DECIMAL(12, 2) NOT NULL,
    current_amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    target_date DATE,
    metric_type VARCHAR(40) NOT NULL DEFAULT 'savings', -- savings, expense_reduction, income_growth
    status VARCHAR(20) NOT NULL DEFAULT 'active',       -- active, completed, archived
    notes VARCHAR(280),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_goals_user_status ON financial_goals(user_id, status, target_date);

-- ==========================================
-- AI Action Checklist
-- ==========================================
CREATE TABLE IF NOT EXISTS ai_action_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    related_period VARCHAR(7) NOT NULL,
    title VARCHAR(180) NOT NULL,
    source_insight VARCHAR(64),
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, done, dismissed
    due_date DATE,
    done_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, related_period, title)
);

CREATE INDEX IF NOT EXISTS idx_ai_actions_user_period ON ai_action_items(user_id, related_period, status);

-- ==========================================
-- Incomes
-- ==========================================
CREATE TABLE IF NOT EXISTS incomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    source VARCHAR(255) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    income_date DATE NOT NULL DEFAULT CURRENT_DATE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_incomes_user_date ON incomes(user_id, income_date);

-- ==========================================
-- Fixed Expenses (real replacement for previous frontend mocks)
-- ==========================================
CREATE TABLE IF NOT EXISTS fixed_expense_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    title VARCHAR(150) NOT NULL,
    category_type VARCHAR(80) DEFAULT 'Diger',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fixed_expense_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES fixed_expense_groups(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    due_day SMALLINT NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fixed_expense_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id UUID NOT NULL REFERENCES fixed_expense_items(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES user_data(id) ON DELETE CASCADE,
    payment_date DATE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'paid', -- paid, pending
    note VARCHAR(280),
    source VARCHAR(40) DEFAULT 'manual',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (item_id, payment_date)
);

CREATE INDEX IF NOT EXISTS idx_fixed_groups_user ON fixed_expense_groups(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_fixed_items_group ON fixed_expense_items(group_id, is_active);
CREATE INDEX IF NOT EXISTS idx_fixed_items_user ON fixed_expense_items(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_fixed_payments_item_date ON fixed_expense_payments(item_id, payment_date);
CREATE INDEX IF NOT EXISTS idx_fixed_payments_user_date ON fixed_expense_payments(user_id, payment_date);
