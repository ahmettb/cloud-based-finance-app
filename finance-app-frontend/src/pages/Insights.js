import React, { useEffect, useMemo, useState } from 'react';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

const currencyFormatter = new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    maximumFractionDigits: 0
});

const defaultMonth = new Date().toISOString().slice(0, 7);

const Insights = () => {
    const toast = useToast();
    const [month, setMonth] = useState(defaultMonth);
    const [loading, setLoading] = useState(true);
    const [overview, setOverview] = useState(null);
    const [analysis, setAnalysis] = useState(null);
    const [goals, setGoals] = useState([]);
    const [savingGoal, setSavingGoal] = useState(false);

    const [aiActions, setAiActions] = useState([]);
    const [actionStats, setActionStats] = useState({ total: 0, done: 0, pending: 0 });

    const [whatIfData, setWhatIfData] = useState(null);
    const [whatIfLoading, setWhatIfLoading] = useState(false);
    const [whatIfCategory, setWhatIfCategory] = useState('');
    const [whatIfCutPercent, setWhatIfCutPercent] = useState(10);

    const [goalForm, setGoalForm] = useState({
        title: '',
        target_amount: '',
        current_amount: '',
        target_date: '',
        metric_type: 'savings'
    });

    const loadWhatIf = async (targetMonth, category = '', cutPercent = 10) => {
        try {
            setWhatIfLoading(true);
            const params = {
                month: targetMonth,
                cut_percent: String(cutPercent)
            };
            if (category) {
                params.category = category;
            }
            const res = await api.getInsightsWhatIf(params);
            setWhatIfData(res);
        } catch (error) {
            console.error(error);
            setWhatIfData(null);
        } finally {
            setWhatIfLoading(false);
        }
    };

    const loadActions = async (targetMonth) => {
        try {
            const res = await api.getAIActions(targetMonth);
            setAiActions(res?.data || []);
            setActionStats(res?.stats || { total: 0, done: 0, pending: 0 });
        } catch (error) {
            console.error(error);
            setAiActions([]);
            setActionStats({ total: 0, done: 0, pending: 0 });
        }
    };

    const loadAll = async () => {
        try {
            setLoading(true);
            const [overviewRes, analysisRes, goalsRes] = await Promise.all([
                api.getInsightsOverview(month),
                api.analyzeSpending({ period: month, useCache: true }),
                api.getGoals()
            ]);

            setOverview(overviewRes);
            setAnalysis(analysisRes);
            setGoals(goalsRes?.data || []);

            const nextActions = analysisRes?.next_actions || [];
            if (nextActions.length > 0) {
                await api.syncAIActions(month, nextActions);
            }

            await Promise.all([
                loadActions(month),
                loadWhatIf(month, '', whatIfCutPercent)
            ]);
        } catch (error) {
            console.error(error);
            toast.show.error('İçgörü verileri yüklenemedi');
            setOverview(null);
            setAnalysis(null);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadAll();
    }, [month]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleCreateGoal = async (e) => {
        e.preventDefault();
        try {
            setSavingGoal(true);
            await api.createGoal({
                title: goalForm.title,
                target_amount: Number(goalForm.target_amount),
                current_amount: Number(goalForm.current_amount || 0),
                target_date: goalForm.target_date || null,
                metric_type: goalForm.metric_type
            });
            toast.show.success('Hedef eklendi');
            setGoalForm({
                title: '',
                target_amount: '',
                current_amount: '',
                target_date: '',
                metric_type: 'savings'
            });
            await loadAll();
        } catch (error) {
            toast.show.error(error.message || 'Hedef eklenemedi');
        } finally {
            setSavingGoal(false);
        }
    };

    const handleGoalProgress = async (goal) => {
        const nextValue = window.prompt('Güncel tutar', String(goal.current_amount || 0));
        if (nextValue === null) return;
        const parsed = Number(nextValue);
        if (Number.isNaN(parsed) || parsed < 0) {
            toast.show.warning('Geçerli bir tutar girin');
            return;
        }
        try {
            await api.updateGoal(goal.id, {
                current_amount: parsed,
                status: parsed >= Number(goal.target_amount || 0) ? 'completed' : 'active'
            });
            toast.show.success('Hedef güncellendi');
            await loadAll();
        } catch (error) {
            toast.show.error(error.message || 'Hedef güncellenemedi');
        }
    };

    const handleArchiveGoal = async (goalId) => {
        try {
            await api.deleteGoal(goalId);
            toast.show.success('Hedef arşivlendi');
            setGoals((prev) => prev.filter((g) => g.id !== goalId));
        } catch (error) {
            toast.show.error(error.message || 'Hedef arşivlenemedi');
        }
    };

    const handleToggleAction = async (action) => {
        const nextStatus = action.status === 'done' ? 'pending' : 'done';
        try {
            await api.updateAIAction(action.id, { status: nextStatus });
            await loadActions(month);
        } catch (error) {
            toast.show.error(error.message || 'Aksiyon güncellenemedi');
        }
    };

    const handleDeleteAction = async (actionId) => {
        try {
            await api.deleteAIAction(actionId);
            await loadActions(month);
        } catch (error) {
            toast.show.error(error.message || 'Aksiyon silinemedi');
        }
    };

    const handleWhatIfRun = async () => {
        await loadWhatIf(month, whatIfCategory, whatIfCutPercent);
    };

    const keyMetrics = useMemo(() => {
        const fh = overview?.financial_health || {};
        const st = overview?.structure || {};
        const gs = overview?.goals || {};
        return [
            { label: 'Tasarruf Oranı', value: `%${fh.savings_rate || 0}`, icon: 'savings', color: 'text-emerald-500', bg: 'bg-emerald-50' },
            { label: 'Aylık Net', value: currencyFormatter.format(fh.net_balance || 0), icon: 'account_balance_wallet', color: 'text-indigo-500', bg: 'bg-indigo-50' },
            { label: 'Abonelik Payı', value: `%${st.subscription_share || 0}`, icon: 'subscriptions', color: 'text-rose-500', bg: 'bg-rose-50' },
            { label: 'Hedef İlerleme', value: `%${gs.active_progress_pct || 0}`, icon: 'flag', color: 'text-amber-500', bg: 'bg-amber-50' }
        ];
    }, [overview]);

    const whatIfCategories = useMemo(() => {
        const fromWhatIf = (whatIfData?.available_categories || []).map((x) => x.name);
        if (fromWhatIf.length > 0) return fromWhatIf;
        return (overview?.structure?.top_categories || []).map((x) => x.name);
    }, [whatIfData, overview]);

    if (loading) {
        return (
            <DashboardLayout>
                <div className="h-full flex flex-col items-center justify-center p-8">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600 mb-4"></div>
                    <p className="text-slate-500 text-sm animate-pulse">Finansal veriler analiz ediliyor...</p>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            {/* Header */}
            <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between bg-white dark:bg-slate-900 p-6 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        <span className="material-icons-round text-indigo-600">psychology</span>
                        Finansal Zeka & İçgörüler
                    </h1>
                    <p className="text-sm text-slate-500 mt-1">Finansal sağlığınız, aksiyon planlarınız ve hedefleriniz tek bir yerde.</p>
                </div>
                <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg">
                    <span className="material-icons-round text-slate-400 ml-2 text-sm">calendar_today</span>
                    <input
                        type="month"
                        value={month}
                        onChange={(e) => setMonth(e.target.value)}
                        className="bg-transparent border-none text-sm font-bold text-slate-700 dark:text-slate-200 focus:ring-0 cursor-pointer"
                    />
                </div>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                {keyMetrics.map((metric) => (
                    <div key={metric.label} className="bg-white dark:bg-slate-900 rounded-2xl p-5 shadow-sm border border-slate-200 dark:border-slate-800 hover:shadow-md transition-shadow">
                        <div className="flex justify-between items-start mb-2">
                            <div className={`p-2 rounded-xl ${metric.bg} ${metric.color}`}>
                                <span className="material-icons-round text-xl">{metric.icon}</span>
                            </div>
                        </div>
                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">{metric.label}</p>
                        <h3 className="text-2xl font-bold mt-1 text-slate-800 dark:text-white">{metric.value}</h3>
                    </div>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left Column */}
                <div className="lg:col-span-2 space-y-8">
                    {/* AI Coach */}
                    <div className="bg-gradient-to-br from-indigo-600 to-violet-700 rounded-2xl p-6 shadow-lg text-white relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity transform scale-150">
                            <span className="material-icons-round text-9xl">auto_awesome</span>
                        </div>
                        <h3 className="font-bold text-lg mb-4 flex items-center gap-2 relative z-10">
                            <span className="material-icons-round">assistant</span>
                            Finansal Asistan Özeti
                        </h3>
                        <div className="relative z-10 bg-white/10 backdrop-blur-sm rounded-xl p-5 border border-white/20">
                            <p className="text-sm leading-relaxed font-medium">
                                "{analysis?.coach?.summary || 'Bu dönem için koç özeti bulunamadı.'}"
                            </p>
                        </div>
                        <div className="mt-4 flex flex-wrap gap-2 relative z-10">
                            {(overview?.recommendations || []).map((item, idx) => (
                                <div key={idx} className="flex items-center gap-1.5 text-xs font-bold bg-white/20 hover:bg-white/30 transition-colors px-3 py-1.5 rounded-full border border-white/10">
                                    <span className="material-icons-round text-[14px]">lightbulb</span>
                                    {item}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* AI Actions */}
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-800">
                        <div className="flex items-center justify-between mb-6">
                            <h3 className="font-bold text-lg text-slate-800 dark:text-white flex items-center gap-2">
                                <span className="material-icons-round text-emerald-500">task_alt</span>
                                Aksiyon Takibi
                            </h3>
                            <div className="flex items-center gap-2 text-xs font-medium bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-full">
                                <span className="text-emerald-600">{actionStats.done} Tamamlanan</span>
                                <span className="text-slate-300">|</span>
                                <span className="text-slate-600">{actionStats.total} Toplam</span>
                            </div>
                        </div>
                        <div className="space-y-3">
                            {aiActions.slice(0, 8).map((action) => (
                                <div
                                    key={action.id}
                                    className={`group p-4 rounded-xl border transition-all ${action.status === 'done'
                                        ? 'bg-slate-50 border-slate-100 dark:bg-slate-800/30 dark:border-slate-800'
                                        : 'bg-white border-slate-200 hover:border-indigo-200 dark:bg-slate-900 dark:border-slate-700'
                                        } flex items-start gap-4`}
                                >
                                    <button
                                        onClick={() => handleToggleAction(action)}
                                        className={`mt-1 w-5 h-5 rounded flex items-center justify-center transition-colors border ${action.status === 'done'
                                            ? 'bg-emerald-500 border-emerald-500 text-white'
                                            : 'border-slate-300 hover:border-indigo-400 text-transparent'
                                            }`}
                                    >
                                        <span className="material-icons-round text-sm">check</span>
                                    </button>
                                    <div className="flex-1">
                                        <p className={`text-sm font-medium transition-colors ${action.status === 'done' ? 'line-through text-slate-400' : 'text-slate-800 dark:text-slate-200'}`}>
                                            {action.title}
                                        </p>
                                        <div className="flex items-center gap-3 mt-1.5">
                                            <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded border ${action.priority === 'HIGH' ? 'bg-red-50 text-red-600 border-red-100' : 'bg-blue-50 text-blue-600 border-blue-100'}`}>
                                                {action.priority === 'HIGH' ? 'Yüksek' : 'Normal'}
                                            </span>
                                            {action.due_date && (
                                                <span className="text-[11px] text-slate-400 flex items-center gap-1">
                                                    <span className="material-icons-round text-[12px]">event</span>
                                                    {action.due_date}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => handleDeleteAction(action.id)}
                                        className="text-slate-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100 p-1"
                                    >
                                        <span className="material-icons-round text-lg">delete_outline</span>
                                    </button>
                                </div>
                            ))}
                            {aiActions.length === 0 && (
                                <div className="text-center py-8 text-slate-400">
                                    <span className="material-icons-round text-4xl mb-2 opacity-20">assignment_turned_in</span>
                                    <p className="text-sm">Henüz bir aksiyon planı oluşturulmadı.</p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Goals */}
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-800">
                        <div className="flex items-center justify-between mb-6">
                            <h3 className="font-bold text-lg text-slate-800 dark:text-white flex items-center gap-2">
                                <span className="material-icons-round text-amber-500">flag</span>
                                Finansal Hedefler
                            </h3>
                            <button className="text-xs font-bold text-indigo-600 hover:text-indigo-700">Tümünü Gör</button>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {goals.map((goal) => {
                                const pct = Math.min(Number(goal.progress_pct || 0), 100);
                                const isCompleted = pct >= 100;
                                return (
                                    <div key={goal.id} className="p-4 rounded-xl border border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 relative overflow-hidden">
                                        {isCompleted && (
                                            <div className="absolute top-0 right-0 p-2">
                                                <span className="material-icons-round text-emerald-500 text-xl">emoji_events</span>
                                            </div>
                                        )}
                                        <div className="flex justify-between items-start mb-2">
                                            <p className="font-bold text-slate-800 dark:text-slate-200">{goal.title}</p>
                                        </div>
                                        <div className="flex items-end justify-between mb-2">
                                            <div>
                                                <p className="text-xs text-slate-500 mb-0.5">İlerleme</p>
                                                <p className="text-sm font-bold text-indigo-600">{currencyFormatter.format(goal.current_amount || 0)}</p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-xs text-slate-500 mb-0.5">Hedef</p>
                                                <p className="text-sm font-medium text-slate-600">{currencyFormatter.format(goal.target_amount || 0)}</p>
                                            </div>
                                        </div>
                                        <div className="relative h-2.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                            <div
                                                className={`absolute top-0 left-0 h-full rounded-full transition-all duration-1000 ${isCompleted ? 'bg-emerald-500' : 'bg-indigo-500'}`}
                                                style={{ width: `${pct}%` }}
                                            ></div>
                                        </div>
                                        <div className="mt-3 flex justify-end gap-2 opacity-80 hover:opacity-100 transition-opacity">
                                            <button onClick={() => handleGoalProgress(goal)} className="text-[10px] font-bold px-2 py-1 rounded bg-white border border-slate-200 hover:bg-slate-50 text-slate-600">
                                                Güncelle
                                            </button>
                                            <button onClick={() => handleArchiveGoal(goal.id)} className="text-[10px] font-bold px-2 py-1 rounded bg-white border border-slate-200 hover:bg-red-50 hover:text-red-600 hover:border-red-100 text-slate-400">
                                                Arşivle
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}
                            {goals.length === 0 && (
                                <div className="col-span-2 text-center py-8 text-slate-400 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                                    <span className="material-icons-round text-3xl mb-1 opacity-20">add_location_alt</span>
                                    <p className="text-sm">Henüz bir hedef belirlemediniz.</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Right Column */}
                <div className="space-y-8">
                    {/* What-if Simulator */}
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-800">
                        <h3 className="font-bold text-lg text-slate-800 dark:text-white mb-4 flex items-center gap-2">
                            <span className="material-icons-round text-violet-500">science</span>
                            Senaryo Simülatörü
                        </h3>
                        <div className="space-y-4">
                            <div>
                                <label className="text-xs font-bold text-slate-500 mb-1.5 block">Kategori Seçimi</label>
                                <select
                                    value={whatIfCategory}
                                    onChange={(e) => setWhatIfCategory(e.target.value)}
                                    className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-4 py-2.5 text-sm font-medium focus:ring-2 focus:ring-violet-500"
                                >
                                    <option value="">En yüksek harcama yapılan</option>
                                    {whatIfCategories.map((name) => <option key={name} value={name}>{name}</option>)}
                                </select>
                            </div>
                            <div>
                                <div className="flex justify-between mb-1.5">
                                    <label className="text-xs font-bold text-slate-500">Tasarruf Hedefi</label>
                                    <span className="text-xs font-bold text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full">%{whatIfCutPercent} Kısıntı</span>
                                </div>
                                <input
                                    type="range"
                                    min="5"
                                    max="40"
                                    step="5"
                                    value={whatIfCutPercent}
                                    onChange={(e) => setWhatIfCutPercent(Number(e.target.value))}
                                    className="w-full accent-violet-600 h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer"
                                />
                                <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                                    <span>%5</span>
                                    <span>%40</span>
                                </div>
                            </div>
                            <button
                                onClick={handleWhatIfRun}
                                className="w-full bg-violet-600 hover:bg-violet-700 text-white py-3 rounded-xl text-sm font-bold shadow-lg shadow-violet-200 transition-all active:scale-95"
                            >
                                Simüle Et
                            </button>
                            {whatIfLoading ? (
                                <p className="text-center text-xs text-slate-400 animate-pulse mt-2">Hesaplanıyor...</p>
                            ) : whatIfData?.scenario && (
                                <div className="mt-2 bg-emerald-50 border border-emerald-100 rounded-xl p-4">
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className="material-icons-round text-emerald-500 text-lg">check_circle</span>
                                        <p className="text-emerald-800 font-bold text-sm">Sonuçlar</p>
                                    </div>
                                    <div className="space-y-1 text-xs text-emerald-700">
                                        <p className="flex justify-between"><span>Hedef Kategori:</span> <span className="font-bold">{whatIfData.scenario.category}</span></p>
                                        <p className="flex justify-between"><span>Potansiyel Tasarruf:</span> <span className="font-bold">{currencyFormatter.format(whatIfData.scenario.estimated_saving || 0)}</span></p>
                                        <div className="h-px bg-emerald-200 my-2"></div>
                                        <p className="flex justify-between items-center">
                                            <span>Yeni Tasarruf Oranı:</span>
                                            <span className="font-bold text-lg">%{whatIfData.scenario.projected_savings_rate ?? 0}</span>
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* New Goal Form */}
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-800">
                        <h3 className="font-bold text-lg text-slate-800 dark:text-white mb-4 flex items-center gap-2">
                            <span className="material-icons-round text-indigo-500">add_circle</span>
                            Yeni Hedef Oluştur
                        </h3>
                        <form onSubmit={handleCreateGoal} className="space-y-4">
                            <div>
                                <label className="text-[10px] font-bold text-slate-500 uppercase mb-1 block">Hedef Başlığı</label>
                                <input
                                    value={goalForm.title}
                                    onChange={(e) => setGoalForm((prev) => ({ ...prev, title: e.target.value }))}
                                    placeholder="Örn: Tatil Birikimi"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500"
                                    required
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-[10px] font-bold text-slate-500 uppercase mb-1 block">Hedef Tutar</label>
                                    <input
                                        type="number"
                                        value={goalForm.target_amount}
                                        onChange={(e) => setGoalForm((prev) => ({ ...prev, target_amount: e.target.value }))}
                                        placeholder="0.00"
                                        className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500"
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="text-[10px] font-bold text-slate-500 uppercase mb-1 block">Mevcut</label>
                                    <input
                                        type="number"
                                        value={goalForm.current_amount}
                                        onChange={(e) => setGoalForm((prev) => ({ ...prev, current_amount: e.target.value }))}
                                        placeholder="0.00"
                                        className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500"
                                    />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-[10px] font-bold text-slate-500 uppercase mb-1 block">Tür</label>
                                    <select
                                        value={goalForm.metric_type}
                                        onChange={(e) => setGoalForm((prev) => ({ ...prev, metric_type: e.target.value }))}
                                        className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500"
                                    >
                                        <option value="savings">Birikim</option>
                                        <option value="expense_reduction">Gider Azaltma</option>
                                        <option value="income_growth">Gelir Artışı</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[10px] font-bold text-slate-500 uppercase mb-1 block">Bitiş Tarihi</label>
                                    <input
                                        type="date"
                                        value={goalForm.target_date}
                                        onChange={(e) => setGoalForm((prev) => ({ ...prev, target_date: e.target.value }))}
                                        className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500"
                                    />
                                </div>
                            </div>
                            <button
                                type="submit"
                                disabled={savingGoal}
                                className="w-full bg-slate-900 hover:bg-slate-800 text-white py-3 rounded-xl text-sm font-bold shadow-lg shadow-slate-200 transition-all active:scale-95 disabled:opacity-70 disabled:cursor-not-allowed"
                            >
                                {savingGoal ? 'Kaydediliyor...' : 'Hedefi Kaydet'}
                            </button>
                        </form>
                    </div>

                    {/* Due Goals Alert */}
                    {(overview?.goals?.due_soon && overview.goals.due_soon.length > 0) && (
                        <div className="bg-amber-50 rounded-2xl p-5 border border-amber-100">
                            <h3 className="font-bold text-sm text-amber-800 mb-3 flex items-center gap-2">
                                <span className="material-icons-round">warning_amber</span>
                                Yaklaşan Hedef Tarihleri
                            </h3>
                            <div className="space-y-2">
                                {overview.goals.due_soon.map((goal) => (
                                    <div key={goal.id} className="text-xs p-3 rounded-xl bg-white/50 border border-amber-100 flex justify-between items-center">
                                        <span className="font-bold text-amber-900">{goal.title}</span>
                                        <span className="text-amber-700 bg-amber-100 px-2 py-0.5 rounded text-[10px] font-bold">{goal.target_date}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Insights;
