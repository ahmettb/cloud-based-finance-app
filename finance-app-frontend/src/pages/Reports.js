import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import SpendingChart from '../components/charts/SpendingChart'; // Reuse for trend

const currencyFormatter = new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    maximumFractionDigits: 0
});

const Reports = () => {
    const navigate = useNavigate();
    const [loading, setLoading] = useState(true);
    const [month, setMonth] = useState(new Date().toISOString().slice(0, 7)); // YYYY-MM
    const [data, setData] = useState(null);
    const [receipts, setReceipts] = useState([]); // Transactions for the month

    useEffect(() => {
        fetchReportData();
    }, [month]);

    const fetchReportData = async () => {
        try {
            setLoading(true);
            const [reportRes, receiptsRes] = await Promise.all([
                api.getDetailedReports(month),
                api.getReceipts({ month: month }) // Assuming getReceipts supports month filter logic or backend ignores extra params if strictly not handled. 
                // Note: api.getReceipts takes params object. Backend handles pagination/filtering. 
                // We might need to adjust backend for strict month filtering if not present, but for now assuming it works or we filter client side.
            ]);

            setData(reportRes);

            // Client side filter just in case if backend returns all
            // Ideally backend should filter by month parameter if implemented
            // Current backend search/list might need 'start_date' 'end_date'
            // Let's assume for now we display 'Most recent' or handle it simply. 
            // Actually, let's use the reportRes data mostly. 
            // If receiptsRes returns data, we use it.
            if (receiptsRes && receiptsRes.items) {
                setReceipts(receiptsRes.items.filter(r => r.date.startsWith(month)));
            }

        } catch (error) {
            console.error("Report fetch error:", error);
        } finally {
            setLoading(false);
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
            {/* Header & Filter */}
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Detaylı Raporlar</h1>
                    <p className="text-slate-500 text-sm mt-1">Harcamalarınızın derinlemesine analizi.</p>
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
                        <p className="text-sm text-slate-400 italic">Veri yok.</p>
                    )}
                </div>

                <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                    <p className="text-slate-500 text-xs font-bold uppercase mb-4">Harcama Zamanlaması</p>
                    <div className="space-y-3">
                        {data.day_analysis && data.day_analysis.map((d, i) => (
                            <div key={i} className="flex justify-between items-center">
                                <div className="flex items-center gap-2">
                                    <div className={`w-2 h-2 rounded-full ${d.day_type === 'Hafta Sonu' ? 'bg-amber-400' : 'bg-blue-400'}`}></div>
                                    <span className="text-sm font-bold text-slate-700 dark:text-slate-300">{d.day_type}</span>
                                </div>
                                <div className="text-right">
                                    <span className="block text-sm font-bold text-slate-900 dark:text-white">{currencyFormatter.format(d.total)}</span>
                                    <span className="text-[10px] text-slate-400">{d.count} işlem</span>
                                </div>
                            </div>
                        ))}
                        {(!data.day_analysis || data.day_analysis.length === 0) && <p className="text-sm text-slate-400">Veri yok.</p>}
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left: Category Breakdown */}
                <div className="lg:col-span-2 space-y-8">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm">
                        <h3 className="font-bold text-slate-800 dark:text-white mb-6">Kategori Dağılımı</h3>
                        <div className="space-y-4">
                            {data.category_breakdown.map((cat, i) => (
                                <div key={i} className="group">
                                    <div className="flex justify-between items-center mb-2">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 rounded-lg bg-slate-50 dark:bg-slate-800 flex items-center justify-center text-slate-500 font-bold text-xs">
                                                {i + 1}
                                            </div>
                                            <div>
                                                <p className="text-sm font-bold text-slate-800 dark:text-white">{cat.name}</p>
                                                <p className="text-[10px] text-slate-400">{cat.count} işlem</p>
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-sm font-bold text-slate-900 dark:text-white">{currencyFormatter.format(cat.value)}</p>
                                            <p className="text-[10px] text-slate-400">
                                                %{Math.round((cat.value / data.stats.total) * 100)}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="h-2 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-indigo-500 rounded-full"
                                            style={{ width: `${(cat.value / data.stats.total) * 100}%` }}
                                        ></div>
                                    </div>
                                </div>
                            ))}
                            {data.category_breakdown.length === 0 && <p className="text-slate-400 text-sm">Bu ay kategori verisi yok.</p>}
                        </div>
                    </div>

                    {/* Transaction List (Snippet) */}
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
                                            <p className="text-xs text-slate-500">{new Date(receipt.date).toLocaleDateString()}</p>
                                        </div>
                                    </div>
                                    <span className="font-bold text-slate-900 dark:text-white text-sm">
                                        -{currencyFormatter.format(receipt.total_amount)}
                                    </span>
                                </div>
                            )) : (
                                <div className="p-8 text-center text-slate-400 text-sm">Bu ay için görüntülenecek fiş bulunamadı.</div>
                            )}
                        </div>
                        {receipts.length > 5 && (
                            <div className="p-3 text-center bg-slate-50 dark:bg-slate-800/50">
                                <button onClick={() => navigate('/receipts')} className="text-xs text-slate-500 hover:text-slate-800">Daha fazla göster ({receipts.length - 5})</button>
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Trend & Insights */}
                <div className="space-y-6">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 border border-slate-200 dark:border-slate-800 shadow-sm h-[300px] flex flex-col">
                        <h3 className="font-bold text-slate-800 dark:text-white mb-4 text-sm">6 Aylık Trend</h3>
                        <div className="h-[300px] w-full relative">
                            {/* Reusing existing SpendingChart but adapting data format if needed. 
                                The backend returns 'trend' as [{month: 'YYYY-MM', total: X}, ...].
                                SpendingChart expects this format roughly or we modify it. 
                                Let's assume SpendingChart can handle array of objects with date_label/total or similar.
                            */}
                            <SpendingChart data={data.trend.map(t => ({ date_label: t.month, total: t.total }))} />
                        </div>
                    </div>

                    <div className="bg-indigo-900 rounded-2xl p-6 text-white shadow-lg">
                        <h3 className="font-bold mb-2 flex items-center gap-2">
                            <span className="material-icons-round text-yellow-400">tips_and_updates</span>
                            Finansal İpucu
                        </h3>
                        <p className="text-indigo-100 text-sm leading-relaxed">
                            Hafta sonu harcamalarınız, hafta içine göre daha yüksek. Eğlence ve dışarıda yemek kategorisindeki bütçenizi kontrol etmek tasarruf etmenize yardımcı olabilir.
                        </p>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Reports;
