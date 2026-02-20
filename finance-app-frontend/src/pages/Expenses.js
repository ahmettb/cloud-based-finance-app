import React, { useEffect, useMemo, useState } from 'react';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';
import {
    CATEGORY_OPTIONS,
    VARIABLE_CATEGORIES,
    FIXED_GROUP_CATEGORIES,
    resolveCategoryId
} from '../constants/categories';

const currencyFormatter = new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    maximumFractionDigits: 0
});

const currentMonth = new Date().toISOString().slice(0, 7);

const categoryIconMap = CATEGORY_OPTIONS.reduce((acc, item) => {
    acc[item.name] = item.icon;
    return acc;
}, {});

const Expenses = () => {
    const toast = useToast();
    const [activeTab, setActiveTab] = useState('fixed');
    const [month, setMonth] = useState(currentMonth);

    const [fixedLoading, setFixedLoading] = useState(true);
    const [fixedGroups, setFixedGroups] = useState([]);
    const [fixedStats, setFixedStats] = useState({ total: 0, paid: 0, remaining: 0, count: 0, pending_count: 0 });

    const [variableLoading, setVariableLoading] = useState(true);
    const [variableExpenses, setVariableExpenses] = useState([]);
    const [variableFilterCategory, setVariableFilterCategory] = useState('all');

    const [aiLoading, setAiLoading] = useState(false);
    const [aiSummary, setAiSummary] = useState(null);

    const [newGroup, setNewGroup] = useState({ title: '', category: 'Fatura' });
    const [newItem, setNewItem] = useState({ group_id: '', name: '', amount: '', day: 1 });
    const [newVariable, setNewVariable] = useState({
        date: new Date().toISOString().split('T')[0],
        category: 'Market',
        merchant: '',
        amount: '',
        description: ''
    });

    const loadFixedExpenses = async (targetMonth) => {
        try {
            setFixedLoading(true);
            const res = await api.getFixedExpenses(targetMonth);
            setFixedGroups(res.data || []);
            setFixedStats(res.stats || { total: 0, paid: 0, remaining: 0, count: 0, pending_count: 0 });
            if (!newItem.group_id && (res.data || []).length > 0) {
                setNewItem((prev) => ({ ...prev, group_id: res.data[0].id }));
            }
        } catch (error) {
            console.error(error);
            toast.show.error('Sabit giderler yuklenemedi');
        } finally {
            setFixedLoading(false);
        }
    };

    const loadVariableExpenses = async (targetMonth) => {
        try {
            setVariableLoading(true);
            const receiptsRes = await api.getReceipts({
                start_date: `${targetMonth}-01`,
                end_date: `${targetMonth}-31`,
                limit: 300
            });
            const rows = (receiptsRes.data || [])
                .filter((r) => r.status !== 'deleted')
                .map((r) => ({
                    id: r.id,
                    date: r.receipt_date,
                    category: r.category || 'Diger',
                    merchant: r.merchant_name || 'Bilinmeyen',
                    amount: Number(r.total_amount || 0),
                    status: r.status
                }))
                .sort((a, b) => new Date(b.date) - new Date(a.date));
            setVariableExpenses(rows);
        } catch (error) {
            console.error(error);
            toast.show.error('Degisken giderler yuklenemedi');
        } finally {
            setVariableLoading(false);
        }
    };

    const loadAISummary = async (targetMonth) => {
        try {
            setAiLoading(true);
            const res = await api.analyzeSpending({ period: targetMonth, useCache: true });
            setAiSummary(res || null);
        } catch (error) {
            console.error(error);
            setAiSummary(null);
        } finally {
            setAiLoading(false);
        }
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        loadFixedExpenses(month);
        loadVariableExpenses(month);
        loadAISummary(month);
    }, [month]); // eslint-disable-line react-hooks/exhaustive-deps

    const variableStats = useMemo(() => {
        const filtered = variableExpenses.filter((e) => {
            if (variableFilterCategory === 'all') return true;
            return e.category === variableFilterCategory;
        });
        const total = filtered.reduce((acc, curr) => acc + Number(curr.amount || 0), 0);
        return { total, count: filtered.length, filtered };
    }, [variableExpenses, variableFilterCategory]);

    const handleCreateGroup = async (e) => {
        e.preventDefault();
        try {
            await api.createFixedExpenseGroup({ title: newGroup.title, category_type: newGroup.category });
            setNewGroup({ title: '', category: 'Fatura' });
            toast.show.success('Grup olusturuldu');
            await loadFixedExpenses(month);
        } catch (error) {
            toast.show.error(error.message || 'Grup olusturulamadi');
        }
    };

    const handleAddItem = async (e) => {
        e.preventDefault();
        try {
            await api.addFixedExpenseItem({
                group_id: newItem.group_id,
                name: newItem.name,
                amount: Number(newItem.amount),
                day: Number(newItem.day)
            });
            setNewItem((prev) => ({ ...prev, name: '', amount: '', day: 1 }));
            toast.show.success('Sabit gider eklendi');
            await loadFixedExpenses(month);
        } catch (error) {
            toast.show.error(error.message || 'Gider eklenemedi');
        }
    };

    const handleStatusToggle = async (item) => {
        try {
            const nextStatus = item.status === 'paid' ? 'pending' : 'paid';
            await api.saveFixedExpensePayment(item.id, {
                month,
                amount: item.amount,
                status: nextStatus,
                source: 'toggle'
            });
            await loadFixedExpenses(month);
        } catch (error) {
            toast.show.error(error.message || 'Odeme durumu guncellenemedi');
        }
    };

    const handleAddHistory = async (item) => {
        const paymentDate = window.prompt('Odeme tarihi (YYYY-MM-DD):', new Date().toISOString().slice(0, 10));
        if (!paymentDate) return;
        const amount = window.prompt('Odeme tutari:', String(item.amount || ''));
        if (!amount) return;

        try {
            await api.saveFixedExpensePayment(item.id, {
                payment_date: paymentDate,
                amount: Number(amount),
                status: 'paid',
                source: 'manual_history'
            });
            toast.show.success('Gecmis odeme eklendi');
            await loadFixedExpenses(month);
        } catch (error) {
            toast.show.error(error.message || 'Gecmis odeme eklenemedi');
        }
    };

    const handleAddVariable = async (e) => {
        e.preventDefault();
        try {
            await api.createManualExpense({
                merchant_name: newVariable.merchant,
                receipt_date: newVariable.date,
                total_amount: Number(newVariable.amount),
                category_id: resolveCategoryId(newVariable.category),
                category_name: newVariable.category,
                description: newVariable.description
            });
            setNewVariable({
                date: new Date().toISOString().split('T')[0],
                category: 'Market',
                merchant: '',
                amount: '',
                description: ''
            });
            toast.show.success('Degisken gider eklendi');
            await loadVariableExpenses(month);
            await loadAISummary(month);
        } catch (error) {
            toast.show.error(error.message || 'Harcama eklenemedi');
        }
    };

    const aiCoachText =
        aiSummary?.coach?.summary ||
        aiSummary?.monthly_summary ||
        'Bu donem icin AI analizi hazir oldugunda burada ozet gorunecek.';

    return (
        <DashboardLayout>
            <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Gider Yonetimi</h1>
                    <p className="text-slate-500 text-sm mt-1">Mock yerine gercek backend verileriyle calisir.</p>
                </div>
                <input type="month" className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs font-bold py-2 px-3" value={month} onChange={(e) => setMonth(e.target.value)} />
            </div>

            <div className="flex gap-4 border-b border-slate-200 dark:border-slate-800 mb-6">
                <button onClick={() => setActiveTab('fixed')} className={`pb-3 px-4 text-sm font-bold transition-all relative ${activeTab === 'fixed' ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}>Sabit Giderler</button>
                <button onClick={() => setActiveTab('variable')} className={`pb-3 px-4 text-sm font-bold transition-all relative ${activeTab === 'variable' ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}>Degisken Giderler</button>
            </div>

            {activeTab === 'fixed' && (
                <div className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-2xl p-5 text-white">
                            <p className="opacity-80 text-xs font-bold uppercase mb-1">Aylik Sabit Yuk</p>
                            <h2 className="text-3xl font-bold tracking-tight">{currencyFormatter.format(fixedStats.total)}</h2>
                        </div>
                        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800">
                            <p className="text-slate-500 text-xs font-bold uppercase">Odenen</p>
                            <h3 className="text-xl font-bold mt-1">{currencyFormatter.format(fixedStats.paid)}</h3>
                        </div>
                        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800">
                            <p className="text-slate-500 text-xs font-bold uppercase">Bekleyen</p>
                            <h3 className="text-xl font-bold mt-1">{fixedStats.pending_count} Adet</h3>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <form onSubmit={handleCreateGroup} className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-200 dark:border-slate-800 space-y-3">
                            <h3 className="font-bold text-sm">Yeni Grup</h3>
                            <input value={newGroup.title} onChange={(e) => setNewGroup({ ...newGroup, title: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" placeholder="Orn: Ev Giderleri" required />
                            <select value={newGroup.category} onChange={(e) => setNewGroup({ ...newGroup, category: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm">
                                {FIXED_GROUP_CATEGORIES.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
                            </select>
                            <button type="submit" className="bg-slate-900 text-white px-4 py-2 rounded-xl text-sm font-bold">Olustur</button>
                        </form>

                        <form onSubmit={handleAddItem} className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-200 dark:border-slate-800 space-y-3">
                            <h3 className="font-bold text-sm">Grupta Yeni Kalem</h3>
                            <select value={newItem.group_id} onChange={(e) => setNewItem({ ...newItem, group_id: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" required>
                                <option value="">Grup secin</option>
                                {fixedGroups.map((g) => <option key={g.id} value={g.id}>{g.title}</option>)}
                            </select>
                            <div className="grid grid-cols-3 gap-2">
                                <input value={newItem.name} onChange={(e) => setNewItem({ ...newItem, name: e.target.value })} className="col-span-2 bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" placeholder="Kalem adi" required />
                                <input type="number" min="1" max="31" value={newItem.day} onChange={(e) => setNewItem({ ...newItem, day: Number(e.target.value) })} className="bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" required />
                            </div>
                            <input type="number" value={newItem.amount} onChange={(e) => setNewItem({ ...newItem, amount: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" placeholder="Tutar" required />
                            <button type="submit" className="bg-indigo-600 text-white px-4 py-2 rounded-xl text-sm font-bold">Ekle</button>
                        </form>
                    </div>

                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                        {fixedLoading ? (
                            <div className="p-8 text-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div></div>
                        ) : fixedGroups.length === 0 ? (
                            <div className="p-8 text-center text-slate-400 text-sm">Sabit gider grubu bulunamadi.</div>
                        ) : (
                            <div className="divide-y divide-slate-100 dark:divide-slate-800">
                                {fixedGroups.map((group) => (
                                    <div key={group.id} className="p-4">
                                        <p className="font-bold text-slate-900 dark:text-white">{group.title}</p>
                                        <p className="text-xs text-slate-400 mb-3">{currencyFormatter.format(group.total_amount || 0)}</p>
                                        <div className="space-y-2">
                                            {group.items.map((item) => (
                                                <div key={item.id} className="flex items-center justify-between bg-slate-50 dark:bg-slate-800/50 rounded-xl px-3 py-2">
                                                    <div>
                                                        <p className="text-sm font-bold">{item.name}</p>
                                                        <p className="text-[11px] text-slate-500">Her ayin {item.day}. gunu • {item.status}</p>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-sm font-bold">{currencyFormatter.format(item.amount)}</span>
                                                        <button onClick={() => handleAddHistory(item)} className="text-xs bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 px-2 py-1 rounded">+Gecmis</button>
                                                        <button onClick={() => handleStatusToggle(item)} className={`text-xs px-2 py-1 rounded ${item.status === 'paid' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{item.status === 'paid' ? 'Odendi' : 'Ode'}</button>
                                                    </div>
                                                </div>
                                            ))}
                                            {group.items.length === 0 && <p className="text-xs text-slate-400">Kalem yok.</p>}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {activeTab === 'variable' && (
                <div className="space-y-6">
                    <div className="bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-slate-800 dark:to-slate-800/50 rounded-2xl p-4 border border-purple-100 dark:border-slate-700">
                        <div className="flex justify-between items-center">
                            <h4 className="font-bold text-sm">Yapay Zeka Ozeti</h4>
                            {aiLoading && <span className="text-[10px] text-slate-500">Yukleniyor...</span>}
                        </div>
                        <p className="text-xs text-slate-600 dark:text-slate-300 mt-2">{aiCoachText}</p>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <form onSubmit={handleAddVariable} className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-200 dark:border-slate-800 space-y-3">
                            <h3 className="font-bold text-sm">Yeni Degisken Gider</h3>
                            <input type="date" value={newVariable.date} onChange={(e) => setNewVariable({ ...newVariable, date: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" required />
                            <input value={newVariable.merchant} onChange={(e) => setNewVariable({ ...newVariable, merchant: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" placeholder="Firma / Yer" required />
                            <select value={newVariable.category} onChange={(e) => setNewVariable({ ...newVariable, category: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm">
                                {VARIABLE_CATEGORIES.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
                            </select>
                            <input type="number" value={newVariable.amount} onChange={(e) => setNewVariable({ ...newVariable, amount: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" placeholder="Tutar" required />
                            <textarea rows="2" value={newVariable.description} onChange={(e) => setNewVariable({ ...newVariable, description: e.target.value })} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm" placeholder="Aciklama" />
                            <button type="submit" className="bg-indigo-600 text-white px-4 py-2 rounded-xl text-sm font-bold">Kaydet</button>
                        </form>

                        <div className="bg-white dark:bg-slate-900 rounded-2xl p-4 border border-slate-200 dark:border-slate-800 space-y-3">
                            <h3 className="font-bold text-sm">Filtre</h3>
                            <select value={variableFilterCategory} onChange={(e) => setVariableFilterCategory(e.target.value)} className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-3 py-2 text-sm">
                                <option value="all">Tum kategoriler</option>
                                {VARIABLE_CATEGORIES.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
                            </select>
                            <p className="text-xs text-slate-500">Toplam: <span className="font-bold">{currencyFormatter.format(variableStats.total)}</span></p>
                            <p className="text-xs text-slate-500">Islem: <span className="font-bold">{variableStats.count}</span></p>
                        </div>
                    </div>

                    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                        {variableLoading ? (
                            <div className="p-8 text-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div></div>
                        ) : variableStats.filtered.length === 0 ? (
                            <div className="p-8 text-center text-slate-400 text-sm">Bu kritere uygun harcama bulunamadi.</div>
                        ) : (
                            <div className="divide-y divide-slate-100 dark:divide-slate-800">
                                {variableStats.filtered.map((expense) => (
                                    <div key={expense.id} className="p-4 flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <span className="material-icons-round text-slate-500">{categoryIconMap[expense.category] || 'category'}</span>
                                            <div>
                                                <p className="text-sm font-bold">{expense.merchant}</p>
                                                <p className="text-[11px] text-slate-500">{expense.date || '-'} • {expense.category}</p>
                                            </div>
                                        </div>
                                        <p className="font-bold">{currencyFormatter.format(expense.amount)}</p>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </DashboardLayout>
    );
};

export default Expenses;



