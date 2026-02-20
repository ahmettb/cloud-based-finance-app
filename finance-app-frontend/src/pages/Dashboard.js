import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/layout/DashboardLayout';
import SpendingChart from '../components/charts/SpendingChart';
import CategoryTrendChart from '../components/charts/CategoryTrendChart'; // New
import VoiceExpenseWizard from '../components/VoiceExpenseWizard';
import ManualExpenseModal from '../components/ManualExpenseModal';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

const currencyFormatter = new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    maximumFractionDigits: 0
});

const formatDateWithDay = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('tr-TR', {
        day: 'numeric',
        month: 'long',
        weekday: 'long'
    });
};

const Dashboard = () => {
    const navigate = useNavigate();
    const toast = useToast();

    // Data States
    const [stats, setStats] = useState(null);
    const [analysis, setAnalysis] = useState(null);
    const [chartData, setChartData] = useState([]);

    // UI States
    const [loading, setLoading] = useState(true);
    const [analyzing, setAnalyzing] = useState(false);
    const [chartRange, setChartRange] = useState('1m'); // 1w, 1m, 3m
    const [chartType, setChartType] = useState('total'); // 'total' or 'category'
    const [showVoiceWizard, setShowVoiceWizard] = useState(false);
    const [showManualWizard, setShowManualWizard] = useState(false);

    // Initial Load
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        const fetchData = async () => {
            try {
                const dashData = await api.getDashboardStats();
                console.log("Dashboard Stats (Raw):", dashData);
                setStats(dashData);
                // Prioritize saved analysis from backend if available
                if (dashData.saved_analysis) {
                    setAnalysis(dashData.saved_analysis);
                }
            } catch (error) {
                console.error("Dashboard fetch error:", error);
                toast.show.error("Veriler yüklenemedi");
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Fetch Chart Data on Range or Type Change
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        const fetchChart = async () => {
            try {
                console.log(`Fetching chart data for Range: ${chartRange}, Type: ${chartType}`);
                const res = await api.getChartData(chartRange, chartType);
                console.log("Chart Data (Raw):", res);
                setChartData(res.data || []);
            } catch (error) {
                console.error("Chart fetch error:", error);
            }
        };
        fetchChart();
    }, [chartRange, chartType]);

    const handleRunAnalysis = async () => {
        try {
            setAnalyzing(true);
            // Run analysis (backend saves it to DB)
            const period = new Date().toISOString().slice(0, 7);
            await api.analyzeSpending({ period, useCache: false, forceRecompute: true });

            // Fetch fresh dashboard data (Single Source of Truth)
            const dashData = await api.getDashboardStats();
            setStats(dashData);

            if (dashData.saved_analysis) {
                setAnalysis(dashData.saved_analysis);
                toast.show.success("Analiz tamamlandı ve güncellendi");
            } else {
                toast.show.warning("Analiz yapıldı ancak sonuç görüntülenemedi");
            }

        } catch (error) {
            console.error("Analysis error:", error);
            toast.show.error("Analiz sırasında hata oluştu");
        } finally {
            setAnalyzing(false);
        }
    };

    const handleVoiceSaved = async () => {
        try {
            const dashData = await api.getDashboardStats();
            setStats(dashData);
            // Also refresh chart
            const chartRes = await api.getChartData(chartRange, chartType);
            setChartData(chartRes.data || []);
        } catch (e) { }
    };

    const handleManualSaved = async () => {
        // Refresh all data
        handleVoiceSaved();
    };

    const categoryList = useMemo(() => {
        const categories = stats?.categories || {};
        const total = stats?.total_spent || 1;

        const colors = ['bg-indigo-500', 'bg-emerald-500', 'bg-amber-500', 'bg-rose-500', 'bg-cyan-500', 'bg-violet-500'];
        const bgColors = ['bg-indigo-50 text-indigo-700', 'bg-emerald-50 text-emerald-700', 'bg-amber-50 text-amber-700', 'bg-rose-50 text-rose-700', 'bg-cyan-50 text-cyan-700', 'bg-violet-50 text-violet-700'];
        const icons = ['shopping_bag', 'restaurant', 'coffee', 'directions_car', 'receipt', 'theater_comedy'];

        return Object.entries(categories)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 5)
            .map(([name, value], idx) => ({
                name,
                value,
                percent: Math.round((value / total) * 100),
                color: bgColors[idx % bgColors.length],
                bar: colors[idx % colors.length],
                bg: bgColors[idx % bgColors.length].split(' ')[0],
                icon: icons[idx % icons.length]
            }));
    }, [stats]);

    if (loading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center h-full">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-600"></div>
                </div>
            </DashboardLayout>
        );
    }

    const netBalance = (stats?.total_income || 0) - (stats?.total_spent || 0);

    return (
        <DashboardLayout>
            {/* Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
                <div>
                    <h1 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        Genel Bakış
                        <span className="text-xs font-normal text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full hidden sm:inline-block">
                            {formatDateWithDay(new Date())}
                        </span>
                    </h1>
                </div>

                {/* AI Analyzing Banner */}
                {analyzing && (
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 animate-gradient-x z-50"></div>
                )}
                {analyzing && (
                    <div className="fixed top-20 left-1/2 transform -translate-x-1/2 bg-slate-900 text-white px-6 py-3 rounded-full shadow-xl flex items-center gap-3 z-50 animate-bounce-slow">
                        <div className="animate-spin rounded-full h-5 w-5 border-2 border-white border-t-transparent"></div>
                        <span className="font-bold text-sm">Yapay Zeka Harcamalarını Analiz Ediyor...</span>
                    </div>
                )}

                <div className="flex gap-2 w-full sm:w-auto">
                    <button
                        onClick={() => setShowVoiceWizard(true)}
                        className="flex-1 sm:flex-none bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded-lg flex items-center justify-center gap-1.5 transition-colors text-xs font-bold shadow-sm shadow-indigo-200"
                    >
                        <span className="material-icons-round text-sm">mic</span>
                        Sesli Harcama
                    </button>
                    <button
                        onClick={() => setShowManualWizard(true)}
                        className="flex-1 sm:flex-none bg-white text-slate-700 hover:bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg flex items-center justify-center gap-1.5 transition-colors text-xs font-bold shadow-sm"
                    >
                        <span className="material-icons-round text-sm">edit</span>
                        Manuel Ekle
                    </button>
                    <button
                        onClick={handleRunAnalysis}
                        disabled={analyzing}
                        className="flex-1 sm:flex-none bg-slate-900 hover:bg-slate-800 text-white px-3 py-1.5 rounded-lg flex items-center justify-center gap-1.5 transition-colors disabled:opacity-70 text-xs font-bold shadow-sm"
                    >
                        <span className="material-icons-round text-xs animate-spin-slow">{analyzing ? 'refresh' : 'auto_awesome'}</span>
                        {analyzing ? 'Analiz...' : 'AI Analiz'}
                    </button>
                </div>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                {/* Income */}
                <div className="p-4 bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="p-1 rounded bg-emerald-50 text-emerald-600"><span className="material-icons-round text-sm">arrow_downward</span></div>
                        <p className="text-slate-500 font-bold text-[10px] uppercase">Toplam Gelir</p>
                    </div>
                    <h2 className="text-xl font-bold text-emerald-600 dark:text-emerald-400 tracking-tight">
                        +{currencyFormatter.format(stats?.total_income || 0)}
                    </h2>
                </div>

                {/* Expense */}
                <div className="p-4 bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="p-1 rounded bg-red-50 text-red-600"><span className="material-icons-round text-sm">arrow_upward</span></div>
                        <p className="text-slate-500 font-bold text-[10px] uppercase">Toplam Gider</p>
                    </div>
                    <h2 className="text-xl font-bold text-red-600 dark:text-red-400 tracking-tight">
                        -{currencyFormatter.format(stats?.total_spent || 0)}
                    </h2>
                </div>

                {/* Net Balance */}
                <div className="p-4 bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="p-1 rounded bg-slate-50 text-slate-600"><span className="material-icons-round text-sm">account_balance_wallet</span></div>
                        <p className="text-slate-500 font-bold text-[10px] uppercase">Net Durum</p>
                    </div>
                    <h2 className={`text-xl font-bold tracking-tight ${netBalance >= 0 ? 'text-slate-900 dark:text-white' : 'text-red-600'}`}>
                        {currencyFormatter.format(netBalance)}
                    </h2>
                </div>

                {/* Forecast */}
                <div className="p-4 bg-white dark:bg-slate-900 rounded-xl shadow-sm border border-indigo-100 dark:border-slate-800 relative overflow-hidden group">
                    <div className="absolute right-0 top-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
                        <span className="material-icons-round text-4xl text-indigo-500">psychology</span>
                    </div>
                    <p className="text-indigo-600 font-bold text-[10px] uppercase mb-1">AI Tahmin (Gelecek Ay)</p>
                    {analysis?.forecast ? (
                        <div>
                            <h2 className="text-xl font-medium text-slate-800 dark:text-slate-200">
                                {currencyFormatter.format(analysis.forecast.next_month_estimate)}
                            </h2>
                            <p className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                                Güven Skoru:
                                <span className="font-bold text-emerald-500">%{analysis.forecast.confidence_score}</span>
                            </p>
                        </div>
                    ) : (
                        analysis ? (
                            <p className="text-xs text-slate-500 italic mt-2">Analiz mevcut ancak tahmin oluşturulamadı.</p>
                        ) : (
                            <p className="text-xs text-slate-400 italic mt-2">Analiz bekleniyor...</p>
                        )
                    )}
                </div>
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">

                {/* Left Column: Chart & Lists */}
                <div className="lg:col-span-2 space-y-6">

                    {/* Filterable Chart Section */}
                    <div className="bg-white dark:bg-slate-900 p-5 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800 flex flex-col min-h-[350px]">
                        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-3">
                            <div className="flex bg-slate-100 dark:bg-slate-800 rounded-lg p-1 w-full sm:w-auto">
                                <button
                                    onClick={() => setChartType('total')}
                                    className={`flex-1 sm:flex-none px-3 py-1.5 text-xs font-bold rounded-md transition-all flex items-center justify-center gap-2 ${chartType === 'total' ? 'bg-white shadow text-slate-900' : 'text-slate-500 hover:text-slate-700'
                                        }`}
                                >
                                    <span className="material-icons-round text-sm">show_chart</span>
                                    Genel
                                </button>
                                <button
                                    onClick={() => setChartType('category')}
                                    className={`flex-1 sm:flex-none px-3 py-1.5 text-xs font-bold rounded-md transition-all flex items-center justify-center gap-2 ${chartType === 'category' ? 'bg-white shadow text-slate-900' : 'text-slate-500 hover:text-slate-700'
                                        }`}
                                >
                                    <span className="material-icons-round text-sm">pie_chart</span>
                                    Kategorik
                                </button>
                            </div>

                            <div className="flex bg-slate-100 dark:bg-slate-800 rounded-lg p-1 w-full sm:w-auto">
                                {['1w', '1m', '3m', '6m'].map((r) => (
                                    <button
                                        key={r}
                                        onClick={() => setChartRange(r)}
                                        className={`flex-1 sm:flex-none px-3 py-1 text-[10px] font-bold rounded-md transition-all ${chartRange === r
                                            ? 'bg-white shadow text-slate-900'
                                            : 'text-slate-500 hover:text-slate-700'
                                            }`}
                                    >
                                        {r === '1w' ? '1 Hafta' : (r === '1m' ? '1 Ay' : (r === '3m' ? '3 Ay' : '6 Ay'))}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div className="w-full h-[300px] mt-4">
                            {chartType === 'total' ? (
                                <SpendingChart data={chartData} />
                            ) : (
                                <CategoryTrendChart data={chartData} />
                            )}
                        </div>
                    </div>

                    {/* Subscriptions & Budgets Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Subscriptions */}
                        <div className="bg-white dark:bg-slate-900 p-5 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800">
                            <div className="flex justify-between items-center mb-4">
                                <h3 className="font-bold text-slate-800 dark:text-white text-sm">Abonelikler</h3>
                            </div>
                            <div className="space-y-3">
                                {stats?.subscriptions?.length > 0 ? stats.subscriptions.map((sub, i) => (
                                    <div key={i} className="flex justify-between items-center text-xs">
                                        <div className="flex items-center gap-2">
                                            <div className="w-6 h-6 rounded-full bg-violet-50 text-violet-600 flex items-center justify-center font-bold text-[10px] uppercase">
                                                {sub.name.charAt(0)}
                                            </div>
                                            <div>
                                                <p className="font-bold text-slate-700">{sub.name}</p>
                                                <p className="text-[10px] text-slate-400">{sub.next_payment_date ? new Date(sub.next_payment_date).toLocaleDateString('tr-TR') : ''}</p>
                                            </div>
                                        </div>
                                        <span className="font-bold text-slate-900">{currencyFormatter.format(sub.amount)}</span>
                                    </div>
                                )) : <p className="text-xs text-slate-400">Abonelik bulunamadı.</p>}
                            </div>
                            <div className="mt-4 pt-3 border-t border-slate-50 dark:border-slate-800">
                                <button onClick={() => navigate('/budget')} className="text-xs font-bold text-indigo-600 hover:text-indigo-700 flex items-center gap-1">
                                    Tümünü Gör <span className="material-icons-round text-xs">arrow_forward</span>
                                </button>
                            </div>
                        </div>

                        {/* Budgets */}
                        <div className="bg-white dark:bg-slate-900 p-5 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800">
                            <div className="flex justify-between items-center mb-4">
                                <h3 className="font-bold text-slate-800 dark:text-white text-sm">Bütçe Hedefleri</h3>
                            </div>
                            <div className="space-y-4">
                                {stats?.budgets?.length > 0 ? stats.budgets.map((b, i) => (
                                    <div key={i}>
                                        <div className="flex justify-between text-[10px] mb-1 font-medium">
                                            <span className="text-slate-700">{b.category_name}</span>
                                            <span className="text-slate-500">{currencyFormatter.format(b.amount)} Limit</span>
                                        </div>
                                        <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                                            <div className="h-full bg-slate-300 w-1/2 rounded-full"></div>
                                        </div>
                                    </div>
                                )) : <p className="text-xs text-slate-400">Bütçe hedefi bulunamadı.</p>}
                            </div>
                            <div className="mt-4 pt-3 border-t border-slate-50 dark:border-slate-800">
                                <button onClick={() => navigate('/budget')} className="text-xs font-bold text-indigo-600 hover:text-indigo-700 flex items-center gap-1">
                                    Detaylı Planlama <span className="material-icons-round text-xs">arrow_forward</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Right Column: Categories & Actions */}
                <div className="space-y-6">
                    {/* AI Insights Card - NEW (Fixed) */}
                    {analysis && (
                        <div className="bg-gradient-to-br from-indigo-50 to-white dark:from-slate-800 dark:to-slate-900 p-5 rounded-xl shadow-sm border border-indigo-100 dark:border-slate-700">
                            <h3 className="font-bold text-indigo-900 dark:text-indigo-200 text-sm mb-3 flex items-center gap-2">
                                <span className="material-icons-round text-indigo-500">auto_awesome</span>
                                AI Finansal Analiz
                            </h3>

                            {/* Headline & Summary from Coach */}
                            {analysis.coach && (
                                <div className="mb-4">
                                    {analysis.coach.headline && (
                                        <p className="font-bold text-slate-800 dark:text-white text-xs mb-1">
                                            {analysis.coach.headline}
                                        </p>
                                    )}
                                    {analysis.coach.summary && (
                                        <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                                            {analysis.coach.summary}
                                        </p>
                                    )}
                                </div>
                            )}

                            {/* Fallback Summary if no coach object */}
                            {!analysis.coach && analysis.summary && typeof analysis.summary === 'string' && (
                                <p className="text-xs text-slate-600 dark:text-slate-300 mb-4 leading-relaxed">
                                    {analysis.summary}
                                </p>
                            )}

                            {/* Fallback Summary if summary is an object (common issue) */}
                            {!analysis.coach && analysis.summary && typeof analysis.summary === 'object' && analysis.summary.total && (
                                <p className="text-xs text-slate-600 dark:text-slate-300 mb-4 leading-relaxed">
                                    Toplam {currencyFormatter.format(analysis.summary.total)} harcama yapıldı.
                                </p>
                            )}

                            {/* Anomalies */}
                            {analysis.anomalies && analysis.anomalies.length > 0 && (
                                <div className="space-y-2 mb-4">
                                    {analysis.anomalies.map((anom, idx) => (
                                        <div key={idx} className="bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800/30 p-2 rounded-lg flex gap-2 items-start">
                                            <span className="material-icons-round text-red-500 text-sm mt-0.5">error_outline</span>
                                            <p className="text-xs text-red-700 dark:text-red-300 font-medium">
                                                {typeof anom === 'string'
                                                    ? anom
                                                    : `${anom.merchant || 'İşlem'} için ${currencyFormatter.format(anom.amount || 0)} tutarlı anomali`}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Insights List */}
                            {analysis.insights && analysis.insights.length > 0 && (
                                <div className="space-y-2">
                                    {analysis.insights.slice(0, 5).map((insight, idx) => {
                                        const txt = typeof insight === 'string'
                                            ? insight
                                            : (insight.summary || insight.title || insight.text || 'AI İçgörü');
                                        const type = typeof insight === 'object' && insight.priority === 'HIGH' ? 'warning' : 'info';
                                        return (
                                            <div key={idx} className="flex gap-2 text-xs text-slate-600 dark:text-slate-400">
                                                <span className="flex-1">{txt}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    )}


                    {/* Categories */}
                    <div className="bg-white dark:bg-slate-900 p-5 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800">
                        <h3 className="font-bold text-slate-800 dark:text-white text-sm mb-4">Kategoriler (Top 5)</h3>
                        <div className="space-y-3">
                            {categoryList.length > 0 ? categoryList.map((cat, idx) => (
                                <div key={idx} className="group">
                                    <div className="flex justify-between items-center mb-1">
                                        <div className="flex items-center gap-2">
                                            <div className={`p-1 rounded-md ${cat.bg}`}>
                                                <span className={`material-icons-round text-xs ${cat.bar.replace('bg-', 'text-')}`}>{cat.icon}</span>
                                            </div>
                                            <span className="text-xs font-bold text-slate-700 dark:text-slate-300">{cat.name}</span>
                                        </div>
                                        <span className="text-xs font-medium text-slate-500 group-hover:text-slate-900 transition-colors">{currencyFormatter.format(cat.value)}</span>
                                    </div>
                                    <div className="h-1 w-full bg-slate-50 dark:bg-slate-800 rounded-full overflow-hidden">
                                        <div className={`h-full rounded-full ${cat.bar}`} style={{ width: `${cat.percent}%` }}></div>
                                    </div>
                                </div>
                            )) : (
                                <p className="text-xs text-slate-400 text-center py-4">Harcama kategorisi bulunamadı.</p>
                            )}
                        </div>
                    </div>

                    {/* AI Actions */}
                    {(analysis?.next_actions?.length > 0) && (
                        <div className="bg-white dark:bg-slate-900 p-5 rounded-xl shadow-sm border border-slate-200 dark:border-slate-800">
                            <h3 className="font-bold text-slate-800 dark:text-white text-sm mb-3">Önerilen Aksiyonlar</h3>
                            <div className="space-y-2">
                                {analysis.next_actions.slice(0, 3).map((action, i) => (
                                    <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
                                        <span className={`h-1.5 w-1.5 rounded-full mt-1.5 shrink-0 ${action.priority === 'HIGH' ? 'bg-red-500' : 'bg-blue-500'}`}></span>
                                        <div>
                                            <p className="text-xs font-medium text-slate-700 dark:text-slate-300 line-clamp-2">{action.title}</p>
                                            <p className="text-[9px] text-slate-400">{action.due_in_days} gün içinde</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {
                showVoiceWizard && (
                    <VoiceExpenseWizard
                        onSave={handleVoiceSaved}
                        onClose={() => setShowVoiceWizard(false)}
                    />
                )
            }

            {
                showManualWizard && (
                    <ManualExpenseModal
                        isOpen={showManualWizard}
                        onClose={() => setShowManualWizard(false)}
                        onSave={handleManualSaved}
                    />
                )
            }
        </DashboardLayout >
    );
};

export default Dashboard;




