import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import SpendingChart from '../components/charts/SpendingChart';

const currencyFormatter = new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    maximumFractionDigits: 0
});

const Reports = () => {
    const navigate = useNavigate();
    const [loading, setLoading] = useState(true);
    const [refreshingAi, setRefreshingAi] = useState(false);
    const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));

    const [data, setData] = useState(null);
    const [aiSummary, setAiSummary] = useState(null);
    const [deepAnalysis, setDeepAnalysis] = useState(null);
    const [receipts, setReceipts] = useState([]);
    const [feedbackState, setFeedbackState] = useState({ sending: false, sent: '' });

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        fetchReportData();
    }, [month]); // eslint-disable-line react-hooks/exhaustive-deps

    const fetchReportData = async () => {
        try {
            setLoading(true);
            const [reportRes, receiptsRes, aiRes, deepRes] = await Promise.all([
                api.getDetailedReports(month),
                api.getReceipts({ start_date: `${month}-01`, end_date: `${month}-31`, limit: 100 }),
                api.getReportAISummary(month),
                api.analyzeSpending({ period: month, useCache: true })
            ]);

            setData(reportRes);
            setAiSummary(aiRes);
            setDeepAnalysis(deepRes);
            setReceipts((receiptsRes?.data || []).filter((r) => String(r?.receipt_date || '').startsWith(month)));
        } catch (error) {
            console.error('Report fetch error:', error);
            setData(null);
            setAiSummary(null);
            setDeepAnalysis(null);
        } finally {
            setLoading(false);
        }
    };

    const refreshDeepAnalysis = async () => {
        try {
            setRefreshingAi(true);
            const res = await api.analyzeSpending({ period: month, useCache: false, forceRecompute: true });
            setDeepAnalysis(res);
        } catch (error) {
            console.error('AI refresh error:', error);
        } finally {
            setRefreshingAi(false);
        }
    };

    const sendFeedback = async (feedbackType) => {
        try {
            setFeedbackState({ sending: true, sent: '' });
            await api.sendReportAIFeedback({
                month,
                feedback_type: feedbackType,
                section: 'monthly_summary'
            });
            setFeedbackState({ sending: false, sent: feedbackType });
        } catch (error) {
            console.error('Feedback send error:', error);
            setFeedbackState({ sending: false, sent: '' });
        }
    };

    if (loading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center h-full">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-600"></div>
                </div>
            </DashboardLayout>
        );
    }

    if (!data) {
        return (
            <DashboardLayout>
                <div className="p-8 text-center text-slate-400">Rapor verisi yuklenemedi.</div>
            </DashboardLayout>
        );
    }

    const anomalies = deepAnalysis?.anomalies || [];
    const nextActions = deepAnalysis?.next_actions || [];

    return (
        <DashboardLayout>
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Detayli Raporlar</h1>
                    <p className="text-slate-500 text-sm mt-1">Aylik harcama trendi, AI ozeti ve aksiyonlar.</p>
                </div>
                <div className="flex items-center gap-2">
                    <input
                        type="month"
                        value={month}
                        onChange={(e) => setMonth(e.target.value)}
                        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-2 text-sm font-bold text-slate-700 dark:text-slate-300"
                    />
                    <button
                        onClick={refreshDeepAnalysis}
                        disabled={refreshingAi}
                        className="bg-slate-900 text-white px-3 py-2 rounded-xl text-xs font-bold"
                    >
                        {refreshingAi ? 'AI...' : 'AI Yenile'}
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="font-bold text-slate-800 dark:text-white flex items-center gap-2">
                            <span className="material-icons-round text-indigo-500">auto_awesome</span>
                            Aylik AI Degerlendirmesi
                        </h3>
                        <span className="text-[11px] font-bold text-slate-400">{aiSummary?.month || month}</span>
                    </div>
                    <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                        {aiSummary?.monthly_summary || deepAnalysis?.coach?.summary || 'Bu ay icin AI degerlendirmesi yok.'}
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2">
                        {(aiSummary?.what_if || []).slice(0, 2).map((item, idx) => (
                            <div key={idx} className="bg-emerald-50 text-emerald-700 border border-emerald-100 rounded-lg px-3 py-2 text-xs">
                                <p className="font-bold">{item.title}</p>
                                <p>Potansiyel tasarruf: {currencyFormatter.format(item.estimated_monthly_saving || 0)}</p>
                            </div>
                        ))}
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                        <button onClick={() => sendFeedback('useful')} disabled={feedbackState.sending} className="text-xs px-3 py-1.5 rounded-lg border border-emerald-200 text-emerald-700 bg-emerald-50">Yararli</button>
                        <button onClick={() => sendFeedback('not_useful')} disabled={feedbackState.sending} className="text-xs px-3 py-1.5 rounded-lg border border-amber-200 text-amber-700 bg-amber-50">Gelismeli</button>
                        {feedbackState.sent && <span className="text-[11px] text-slate-400">Geri bildirim kaydedildi.</span>}
                    </div>
                </div>

                <div className="bg-gradient-to-br from-indigo-500 to-violet-600 rounded-2xl p-6 text-white shadow-lg shadow-indigo-200 dark:shadow-none">
                    <p className="opacity-80 text-xs font-bold uppercase mb-2">Risk Skoru</p>
                    <h2 className="text-4xl font-bold tracking-tight">{aiSummary?.risk_score ?? '-'}</h2>
                    <p className="text-xs opacity-90 mt-2">0 dusuk risk / 100 yuksek risk</p>
                    <div className="mt-4 text-[11px] opacity-85">Guven: %{aiSummary?.meta?.confidence ?? 0}</div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="bg-gradient-to-br from-indigo-500 to-violet-600 rounded-2xl p-6 text-white">
                    <p className="opacity-80 text-xs font-bold uppercase mb-2">Toplam Harcama</p>
                    <h2 className="text-3xl font-bold tracking-tight">{currencyFormatter.format(data.stats.total)}</h2>
                    <p className="text-xs mt-2">{data.stats.count} islem • Ort. {currencyFormatter.format(data.stats.avg)}</p>
                </div>
                <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                    <p className="text-slate-500 text-xs font-bold uppercase mb-2">AI Forecast</p>
                    <h2 className="text-2xl font-bold text-slate-900 dark:text-white">{deepAnalysis?.forecast?.next_month_estimate ? currencyFormatter.format(deepAnalysis.forecast.next_month_estimate) : '-'}</h2>
                    <p className="text-xs text-slate-400 mt-1">Trend: {deepAnalysis?.forecast?.trend || '-'}</p>
                </div>
                <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                    <p className="text-slate-500 text-xs font-bold uppercase mb-2">Anomali Sayisi</p>
                    <h2 className="text-2xl font-bold text-slate-900 dark:text-white">{anomalies.length}</h2>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                        <h3 className="font-bold text-slate-800 dark:text-white mb-4">Kategori Dagilimi</h3>
                        <div className="space-y-4">
                            {data.category_breakdown.map((cat, idx) => (
                                <div key={idx}>
                                    <div className="flex justify-between mb-1 text-sm">
                                        <div>
                                            <p className="font-bold">{cat.name}</p>
                                            <p className="text-xs text-slate-400">{cat.count} islem</p>
                                        </div>
                                        <p className="font-bold">{currencyFormatter.format(cat.value)}</p>
                                    </div>
                                    <div className="h-2 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                        <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${(cat.value / (data.stats.total || 1)) * 100}%` }}></div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                        <div className="p-6 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
                            <h3 className="font-bold text-slate-800 dark:text-white">Ayin Harcamalari</h3>
                            <button onClick={() => navigate('/receipts')} className="text-xs font-bold text-indigo-600">Tumunu Yonet</button>
                        </div>
                        <div className="divide-y divide-slate-100 dark:divide-slate-800">
                            {receipts.length > 0 ? receipts.slice(0, 8).map((receipt) => (
                                <div key={receipt.id} className="p-4 flex justify-between items-center">
                                    <div>
                                        <p className="font-bold text-sm">{receipt.merchant_name || 'Bilinmeyen'}</p>
                                        <p className="text-xs text-slate-500">{receipt.receipt_date || '-'}</p>
                                    </div>
                                    <span className="font-bold text-sm">-{currencyFormatter.format(receipt.total_amount || 0)}</span>
                                </div>
                            )) : <div className="p-8 text-center text-slate-400 text-sm">Bu ay fis bulunamadi.</div>}
                        </div>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm h-[300px]">
                        <h3 className="font-bold text-slate-800 dark:text-white mb-4 text-sm">6 Aylik Trend</h3>
                        <div className="h-[220px] w-full">
                            <SpendingChart data={data.trend.map((t) => ({ date_label: t.month, total: t.total }))} />
                        </div>
                    </div>

                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                        <h3 className="font-bold mb-3 text-slate-800 dark:text-white">Onerilen AI Aksiyonlari</h3>
                        <div className="space-y-2">
                            {nextActions.length > 0 ? nextActions.slice(0, 5).map((action, idx) => (
                                <div key={idx} className="text-xs border border-slate-100 dark:border-slate-800 rounded-lg p-2">
                                    <p className="font-bold">{action.title}</p>
                                    <p className="text-slate-500 mt-1">{action.priority} • {action.due_in_days} gun</p>
                                </div>
                            )) : <p className="text-slate-400 text-sm">Aksiyon verisi yok.</p>}
                        </div>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Reports;



