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
    const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
    const [data, setData] = useState(null);
    const [aiSummary, setAiSummary] = useState(null);
    const [receipts, setReceipts] = useState([]);
    const [feedbackState, setFeedbackState] = useState({ sending: false, sent: '' });

    useEffect(() => {
        fetchReportData();
    }, [month]);

    const fetchReportData = async () => {
        try {
            setLoading(true);
            const [reportRes, receiptsRes, aiRes] = await Promise.all([
                api.getDetailedReports(month),
                api.getReceipts({ start_date: `${month}-01`, end_date: `${month}-31`, limit: 50 }),
                api.getReportAISummary(month)
            ]);

            setData(reportRes);
            setAiSummary(aiRes);

            const list = receiptsRes?.data || [];
            const filtered = list.filter((r) => String(r?.receipt_date || '').startsWith(month));
            setReceipts(filtered);
        } catch (error) {
            console.error('Report fetch error:', error);
            setAiSummary(null);
        } finally {
            setLoading(false);
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

    if (!data) return null;

    return (
        <DashboardLayout>
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Detaylı Raporlar</h1>
                    <p className="text-slate-500 text-sm mt-1">Harcamalarınızın derinlemesine analizi ve aylık AI değerlendirmesi.</p>
                </div>
                <div>
                    <input
                        type="month"
                        value={month}
                        onChange={(e) => setMonth(e.target.value)}
                        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-2 text-sm font-bold text-slate-700 dark:text-slate-300 shadow-sm outline-none focus:ring-2 focus:ring-indigo-500/20"
                    />
                </div>
            </div>

            {/* AI Monthly Summary */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="font-bold text-slate-800 dark:text-white flex items-center gap-2">
                            <span className="material-icons-round text-indigo-500">auto_awesome</span>
                            Aylık AI Değerlendirmesi
                        </h3>
                        <span className="text-[11px] font-bold text-slate-400">{aiSummary?.month || month}</span>
                    </div>
                    <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                        {aiSummary?.monthly_summary || 'Bu ay için yeterli AI değerlendirme verisi bulunamadı.'}
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
                        <button
                            onClick={() => sendFeedback('useful')}
                            disabled={feedbackState.sending}
                            className="text-xs px-3 py-1.5 rounded-lg border border-emerald-200 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 disabled:opacity-50"
                        >
                            👍 Yararlı
                        </button>
                        <button
                            onClick={() => sendFeedback('not_useful')}
                            disabled={feedbackState.sending}
                            className="text-xs px-3 py-1.5 rounded-lg border border-amber-200 text-amber-700 bg-amber-50 hover:bg-amber-100 disabled:opacity-50"
                        >
                            👎 Geliştirilmeli
                        </button>
                        {feedbackState.sent && (
                            <span className="text-[11px] text-slate-400">Geri bildirimin kaydedildi.</span>
                        )}
                    </div>
                </div>

                <div className="bg-gradient-to-br from-indigo-500 to-violet-600 rounded-2xl p-6 text-white shadow-lg shadow-indigo-200 dark:shadow-none">
                    <p className="opacity-80 text-xs font-bold uppercase mb-2">Risk Skoru</p>
                    <h2 className="text-4xl font-bold tracking-tight">{aiSummary?.risk_score ?? '-'}</h2>
                    <p className="text-xs opacity-90 mt-2">0 düşük risk / 100 yüksek risk</p>
                    <div className="mt-4 text-[11px] opacity-85">
                        Güven: %{aiSummary?.meta?.confidence ?? 0}
                    </div>
                </div>
            </div>

            {/* Top Stats Row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="bg-gradient-to-br from-indigo-500 to-violet-600 rounded-2xl p-6 text-white shadow-lg shadow-indigo-200 dark:shadow-none">
                    <p className="opacity-80 text-xs font-bold uppercase mb-2">Toplam Harcama</p>
                    <h2 className="text-3xl font-bold tracking-tight">{currencyFormatter.format(data.stats.total)}</h2>
                    <div className="mt-4 flex items-center gap-2 text-sm opacity-90">
                        <span className="bg-white/20 px-2 py-0.5 rounded text-xs font-bold">{data.stats.count} İşlem</span>
                        <span className="text-xs">Ort. {currencyFormatter.format(data.stats.avg)}</span>
                    </div>
                </div>

                <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm relative overflow-hidden">
                    <div className="absolute right-0 top-0 p-4 opacity-5">
                        <span className="material-icons-round text-6xl text-red-500">priority_high</span>
                    </div>
                    <p className="text-slate-500 text-xs font-bold uppercase mb-2">Ayın En Yüksek Harcaması</p>
                    {data.highest_expense ? (
                        <>
                            <h2 className="text-2xl font-bold text-slate-800 dark:text-white mb-1">
                                {currencyFormatter.format(data.highest_expense.total_amount)}
                            </h2>
                            <p className="font-bold text-slate-600 dark:text-slate-400 text-sm truncate">{data.highest_expense.merchant_name}</p>
                            <div className="flex items-center gap-2 mt-3">
                                <span className="text-[10px] bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-md text-slate-500 font-bold uppercase">
                                    {data.highest_expense.category_name}
                                </span>
                                <span className="text-[10px] text-slate-400">
                                    {new Date(data.highest_expense.receipt_date).toLocaleDateString()}
                                </span>
                            </div>
                        </>
                    ) : (
                        <p className="text-slate-400 text-sm">Bu ay işlem bulunamadı.</p>
                    )}
                </div>

                <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                    <p className="text-slate-500 text-xs font-bold uppercase mb-2">Kritik AI Olayları</p>
                    <div className="space-y-2">
                        {(aiSummary?.critical_events || []).slice(0, 2).map((event) => (
                            <div key={event.id} className="bg-rose-50 border border-rose-100 rounded-lg p-2">
                                <p className="text-xs font-bold text-rose-700">{event.title}</p>
                                <p className="text-[11px] text-rose-600">{event.merchant} · {currencyFormatter.format(event.amount || 0)}</p>
                            </div>
                        ))}
                        {!aiSummary?.critical_events?.length && <p className="text-slate-400 text-sm">Kritik olay yok.</p>}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                        <h3 className="font-bold text-slate-800 dark:text-white mb-4">Kategori Dağılımı</h3>
                        <div className="space-y-4">
                            {data.category_breakdown.map((cat, idx) => (
                                <div key={idx}>
                                    <div className="flex justify-between mb-1 text-sm">
                                        <div>
                                            <p className="font-bold text-slate-700 dark:text-slate-300">{cat.name}</p>
                                            <p className="text-xs text-slate-400">{cat.count} işlem</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-sm font-bold text-slate-900 dark:text-white">{currencyFormatter.format(cat.value)}</p>
                                            <p className="text-[10px] text-slate-400">%{Math.round((cat.value / (data.stats.total || 1)) * 100)}</p>
                                        </div>
                                    </div>
                                    <div className="h-2 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                        <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${(cat.value / (data.stats.total || 1)) * 100}%` }}></div>
                                    </div>
                                </div>
                            ))}
                            {data.category_breakdown.length === 0 && <p className="text-slate-400 text-sm">Bu ay kategori verisi yok.</p>}
                        </div>
                    </div>

                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                        <div className="p-6 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
                            <h3 className="font-bold text-slate-800 dark:text-white">Ayın Harcamaları</h3>
                            <button onClick={() => navigate('/receipts')} className="text-xs font-bold text-indigo-600 hover:text-indigo-700">Tümünü Yönet</button>
                        </div>
                        <div className="divide-y divide-slate-100 dark:divide-slate-800">
                            {receipts.length > 0 ? receipts.slice(0, 5).map(receipt => (
                                <div key={receipt.id} className="p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex justify-between items-center">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-500">
                                            <span className="material-icons-round text-lg">receipt</span>
                                        </div>
                                        <div>
                                            <p className="font-bold text-slate-800 dark:text-white text-sm">{receipt.merchant_name || 'Bilinmeyen'}</p>
                                            <p className="text-xs text-slate-500">{receipt.receipt_date ? new Date(receipt.receipt_date).toLocaleDateString() : '-'}</p>
                                        </div>
                                    </div>
                                    <span className="font-bold text-slate-900 dark:text-white text-sm">-{currencyFormatter.format(receipt.total_amount)}</span>
                                </div>
                            )) : (
                                <div className="p-8 text-center text-slate-400 text-sm">Bu ay için görüntülenecek fiş bulunamadı.</div>
                            )}
                        </div>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm h-[300px] flex flex-col">
                        <h3 className="font-bold text-slate-800 dark:text-white mb-4 text-sm">6 Aylık Trend</h3>
                        <div className="h-[300px] w-full relative">
                            <SpendingChart data={data.trend.map(t => ({ date_label: t.month, total: t.total }))} />
                        </div>
                    </div>

                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                        <h3 className="font-bold mb-3 text-slate-800 dark:text-white flex items-center gap-2">
                            <span className="material-icons-round text-violet-500">storefront</span>
                            Satıcı Sıklığı (AI)
                        </h3>
                        <div className="space-y-2">
                            {(aiSummary?.merchant_frequency || []).slice(0, 4).map((m, idx) => (
                                <div key={idx} className="flex items-center justify-between text-xs border border-slate-100 dark:border-slate-800 rounded-lg p-2">
                                    <div>
                                        <p className="font-bold text-slate-700 dark:text-slate-300">{m.merchant}</p>
                                        <p className="text-slate-400">{m.tx_count} işlem</p>
                                    </div>
                                    <p className="font-bold text-slate-900 dark:text-white">{currencyFormatter.format(m.total || 0)}</p>
                                </div>
                            ))}
                            {!aiSummary?.merchant_frequency?.length && <p className="text-slate-400 text-sm">Sıklık verisi yok.</p>}
                        </div>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Reports;
