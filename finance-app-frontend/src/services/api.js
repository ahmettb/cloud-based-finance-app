import { API_BASE_URL } from '../config';

const API_DEBUG = process.env.REACT_APP_API_DEBUG === 'true';

const getHeaders = (token) => ({
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
});

const fetchWithAuth = async (endpoint, options = {}) => {
    let token = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');
    const url = `${API_BASE_URL}${endpoint}`;

    let debugBody = '';
    if (options.body) {
        try {
            debugBody = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
        } catch (e) {
            debugBody = options.body;
        }
    }
    if (API_DEBUG) {
        console.log(`API Request [${options.method || 'GET'}]: ${endpoint}`, debugBody);
    }

    let response = await fetch(url, {
        ...options,
        headers: {
            ...getHeaders(token),
            ...options.headers,
        },
    });

    if (response.status === 401 && refreshToken) {
        if (API_DEBUG) {
            console.log('Token expired, refreshing...');
        }
        try {
            const refreshResponse = await fetch(`${API_BASE_URL}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
            });

            if (refreshResponse.ok) {
                const data = await refreshResponse.json();
                const newTokens = data.tokens || data;

                localStorage.setItem('access_token', newTokens.access_token);
                if (newTokens.id_token) localStorage.setItem('id_token', newTokens.id_token);

                token = newTokens.access_token;
                response = await fetch(url, {
                    ...options,
                    headers: {
                        ...getHeaders(token),
                        ...options.headers,
                    },
                });
            } else {
                localStorage.clear();
                window.location.href = '/login';
                throw new Error('Session expired');
            }
        } catch (e) {
            localStorage.clear();
            window.location.href = '/login';
            throw e;
        }
    }

    let responseData;
    try {
        responseData = await response.json();
    } catch (e) {
        responseData = {};
    }

    if (!response.ok) {
        console.error(`API Error [${response.status}]: ${endpoint}`, responseData);
        throw new Error(responseData.error || `HTTP error! status: ${response.status}`);
    }

    if (API_DEBUG) {
        console.log(`API Response [${endpoint}]:`, responseData);
    }
    return responseData;
};

export const api = {
    login: async (email, password) => {
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Login failed');
        }

        const data = await response.json();
        localStorage.setItem('access_token', data.tokens.access_token);
        localStorage.setItem('id_token', data.tokens.id_token);
        localStorage.setItem('refresh_token', data.tokens.refresh_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        return data;
    },

    register: async (email, password, full_name) => {
        const response = await fetch(`${API_BASE_URL}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, full_name }),
        });
        if (!response.ok) throw new Error('Registration failed');
        return response.json();
    },

    logout: () => {
        localStorage.clear();
        window.location.href = '/login';
    },

    getCurrentUser: () => {
        try {
            return JSON.parse(localStorage.getItem('user'));
        } catch (e) {
            return null;
        }
    },

    getDashboardStats: () => fetchWithAuth('/dashboard'),

    analyzeSpending: (data = {}) => fetchWithAuth('/analyze', {
        method: 'POST',
        body: JSON.stringify(data)
    }),

    getBudgets: () => fetchWithAuth('/budgets'),
    setBudget: (data) => fetchWithAuth('/budgets', { method: 'POST', body: JSON.stringify(data) }),
    deleteBudget: (id) => fetchWithAuth(`/budgets/${id}`, { method: 'DELETE' }),

    getSubscriptions: () => fetchWithAuth('/subscriptions'),
    addSubscription: (data) => fetchWithAuth('/subscriptions', { method: 'POST', body: JSON.stringify(data) }),
    deleteSubscription: (id) => fetchWithAuth(`/subscriptions/${id}`, { method: 'DELETE' }),

    getFixedExpenses: (month) => {
        const query = month ? `?month=${month}` : '';
        return fetchWithAuth(`/fixed-expenses${query}`);
    },
    createFixedExpenseGroup: (data) => fetchWithAuth('/fixed-expenses/groups', {
        method: 'POST',
        body: JSON.stringify(data)
    }),
    updateFixedExpenseGroup: (groupId, data) => fetchWithAuth(`/fixed-expenses/groups/${groupId}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    }),
    deleteFixedExpenseGroup: (groupId) => fetchWithAuth(`/fixed-expenses/groups/${groupId}`, {
        method: 'DELETE'
    }),
    addFixedExpenseItem: (data) => fetchWithAuth('/fixed-expenses/items', {
        method: 'POST',
        body: JSON.stringify(data)
    }),
    updateFixedExpenseItem: (itemId, data) => fetchWithAuth(`/fixed-expenses/items/${itemId}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    }),
    deleteFixedExpenseItem: (itemId) => fetchWithAuth(`/fixed-expenses/items/${itemId}`, {
        method: 'DELETE'
    }),
    saveFixedExpensePayment: (itemId, data) => fetchWithAuth(`/fixed-expenses/items/${itemId}/payments`, {
        method: 'POST',
        body: JSON.stringify(data)
    }),

    exportData: async () => {
        const meta = await fetchWithAuth('/export');
        if (!meta.download_url) throw new Error('Download URL not found');

        const response = await fetch(meta.download_url);
        if (!response.ok) throw new Error('Failed to download export file');
        return response.blob();
    },

    getReceipts: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchWithAuth(`/receipts?${query}`);
    },

    getReceiptDetail: (id) => fetchWithAuth(`/receipts/${id}`),

    createManualExpense: (data) => fetchWithAuth('/receipts/manual', {
        method: 'POST',
        body: JSON.stringify(data)
    }),

    extractSmartData: (text) => fetchWithAuth('/receipts/smart-extract', {
        method: 'POST',
        body: JSON.stringify({ text })
    }),

    getChartData: (range, type = 'total') => fetchWithAuth(`/reports/chart?range=${range}&type=${type}`),

    getDetailedReports: (month) => fetchWithAuth(`/reports/detailed?month=${month}`),

    getReportAISummary: (month) => fetchWithAuth(`/reports/ai-summary?month=${month}`),

    sendReportAIFeedback: (data) => fetchWithAuth('/reports/ai-feedback', {
        method: 'POST',
        body: JSON.stringify(data)
    }),

    getReportsSummary: (months = 12) => fetchWithAuth(`/reports/summary?months=${months}`),

    getInsightsOverview: (month) => {
        const query = month ? `?month=${month}` : '';
        return fetchWithAuth(`/insights/overview${query}`);
    },
    getInsightsWhatIf: (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return fetchWithAuth(`/insights/what-if?${query}`);
    },

    getAIActions: (month) => {
        const query = month ? `?month=${month}` : '';
        return fetchWithAuth(`/ai-actions${query}`);
    },
    syncAIActions: (month, actions = []) => fetchWithAuth('/ai-actions', {
        method: 'POST',
        body: JSON.stringify({ month, actions })
    }),
    updateAIAction: (id, data) => fetchWithAuth(`/ai-actions/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data)
    }),
    deleteAIAction: (id) => fetchWithAuth(`/ai-actions/${id}`, {
        method: 'DELETE'
    }),
    applyAIAction: (id, data) => fetchWithAuth(`/ai-actions/${id}/apply`, {
        method: 'POST',
        body: JSON.stringify(data)
    }),

    // Receipt Items CRUD
    addReceiptItem: (receiptId, data) => fetchWithAuth(`/receipts/${receiptId}/items`, {
        method: 'POST',
        body: JSON.stringify(data)
    }),
    updateReceiptItem: (receiptId, itemId, data) => fetchWithAuth(`/receipts/${receiptId}/items/${itemId}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    }),
    deleteReceiptItem: (receiptId, itemId) => fetchWithAuth(`/receipts/${receiptId}/items/${itemId}`, {
        method: 'DELETE'
    }),

    getGoals: () => fetchWithAuth('/goals'),
    createGoal: (data) => fetchWithAuth('/goals', {
        method: 'POST',
        body: JSON.stringify(data)
    }),
    updateGoal: (id, data) => fetchWithAuth(`/goals/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    }),
    deleteGoal: (id) => fetchWithAuth(`/goals/${id}`, {
        method: 'DELETE'
    }),

    uploadReceipt: async (file) => {
        try {
            // 1. Get Presigned URL
            const initData = await fetchWithAuth('/receipts/upload', {
                method: 'POST',
                body: JSON.stringify({
                    filename: file.name,
                    content_type: file.type
                }),
            });

            if (!initData.upload_url) throw new Error('Upload URL alınamadı');

            // 2. Upload to S3
            const s3Response = await fetch(initData.upload_url, {
                method: 'PUT',
                headers: { 'Content-Type': file.type },
                body: file,
            });

            if (!s3Response.ok) throw new Error('Dosya S3\'e yüklenirken hata oluştu');

            // 3. Process with AI
            const processData = await fetchWithAuth(`/receipts/${initData.receipt_id}/process`, {
                method: 'POST',
                body: JSON.stringify({})
            });

            return {
                ...initData,
                process: processData
            };
        } catch (error) {
            console.error("Upload flow error:", error);
            throw error;
        }
    },

    deleteReceipt: (id) => fetchWithAuth(`/receipts/${id}`, { method: 'DELETE' }),

    // Incomes
    getIncomes: () => fetchWithAuth('/incomes'),

    addIncome: (data) => fetchWithAuth('/incomes', {
        method: 'POST',
        body: JSON.stringify(data)
    }),

    deleteIncome: (id) => fetchWithAuth(`/incomes/${id}`, { method: 'DELETE' }),

    updateIncome: (id, data) => fetchWithAuth(`/incomes/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    }),

    updateSubscription: (id, data) => fetchWithAuth(`/subscriptions/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    }),

    updateReceipt: (id, data) => fetchWithAuth(`/receipts/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data)
    })
};
