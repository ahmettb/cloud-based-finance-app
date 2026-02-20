import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import { VARIABLE_CATEGORIES } from '../constants/categories';

const Planning = () => {
    const [activeTab, setActiveTab] = useState('budget');
    const [budgets, setBudgets] = useState([]);
    const [subscriptions, setSubscriptions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState({ type: '', text: '' });

    const [budgetForm, setBudgetForm] = useState({ category_name: 'Market', amount: '' });
    const [subForm, setSubForm] = useState({ name: '', amount: '', next_payment_date: '' });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            setLoading(true);
            const [bRes, sRes] = await Promise.all([api.getBudgets(), api.getSubscriptions()]);
            setBudgets(bRes.data || []);
            setSubscriptions(sRes.data || []);
        } catch (error) {
            console.error(error);
            setMessage({ type: 'error', text: 'Veriler yuklenemedi.' });
        } finally {
            setLoading(false);
        }
    };

    const handleBudgetSubmit = async (e) => {
        e.preventDefault();
        try {
            await api.setBudget({
                category_name: budgetForm.category_name,
                amount: parseFloat(budgetForm.amount)
            });
            setMessage({ type: 'success', text: 'Butce hedefi guncellendi.' });
            setBudgetForm((prev) => ({ ...prev, amount: '' }));
            fetchData();
        } catch (error) {
            setMessage({ type: 'error', text: 'Butce guncellenemedi.' });
        }
    };

    const handleSubSubmit = async (e) => {
        e.preventDefault();
        try {
            await api.addSubscription({
                name: subForm.name,
                amount: parseFloat(subForm.amount),
                next_payment_date: subForm.next_payment_date
            });
            setMessage({ type: 'success', text: 'Abonelik eklendi.' });
            setSubForm({ name: '', amount: '', next_payment_date: '' });
            fetchData();
        } catch (error) {
            setMessage({ type: 'error', text: 'Abonelik eklenemedi.' });
        }
    };

    const handleDeleteSubscription = async (id) => {
        try {
            await api.deleteSubscription(id);
            setSubscriptions((prev) => prev.filter((s) => String(s.id) !== String(id)));
            setMessage({ type: 'success', text: 'Abonelik silindi.' });
        } catch (error) {
            setMessage({ type: 'error', text: 'Abonelik silinemedi.' });
        }
    };

    if (loading) {
        return (
            <DashboardLayout>
                <div className="h-56 flex items-center justify-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-[#135bec]"></div>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="mb-8">
                <h1 className="text-2xl font-bold text-[#111318] dark:text-white">Planlama ve Yonetim</h1>
                <p className="text-slate-500 text-sm">Butce hedeflerini ve duzenli odemeleri yonetin.</p>
            </div>

            <div className="flex gap-4 border-b border-slate-200 dark:border-slate-800 mb-8">
                <button onClick={() => setActiveTab('budget')} className={`pb-3 px-4 text-sm font-bold ${activeTab === 'budget' ? 'text-[#135bec] border-b-2 border-[#135bec]' : 'text-slate-500'}`}>Butce Hedefleri</button>
                <button onClick={() => setActiveTab('subscription')} className={`pb-3 px-4 text-sm font-bold ${activeTab === 'subscription' ? 'text-[#135bec] border-b-2 border-[#135bec]' : 'text-slate-500'}`}>Abonelik Takibi</button>
            </div>

            {message.text && (
                <div className={`mb-6 p-4 rounded-xl text-sm font-bold flex items-center gap-2 ${message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                    <span className="material-icons-round">{message.type === 'success' ? 'check_circle' : 'error'}</span>
                    {message.text}
                    <button onClick={() => setMessage({ type: '', text: '' })} className="ml-auto material-icons-round text-sm opacity-50 hover:opacity-100">close</button>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="bg-white dark:bg-[#101622] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm h-fit">
                    <h3 className="font-bold text-lg text-[#111318] dark:text-white mb-6">{activeTab === 'budget' ? 'Yeni Butce Hedefi' : 'Abonelik Ekle'}</h3>

                    {activeTab === 'budget' ? (
                        <form onSubmit={handleBudgetSubmit} className="space-y-4">
                            <select className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm" value={budgetForm.category_name} onChange={(e) => setBudgetForm({ ...budgetForm, category_name: e.target.value })}>
                                {VARIABLE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                            </select>
                            <input type="number" className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm" placeholder="Aylik limit" value={budgetForm.amount} onChange={(e) => setBudgetForm({ ...budgetForm, amount: e.target.value })} required />
                            <button type="submit" className="w-full bg-[#135bec] text-white font-bold py-3 rounded-xl">Kaydet</button>
                        </form>
                    ) : (
                        <form onSubmit={handleSubSubmit} className="space-y-4">
                            <input type="text" className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm" placeholder="Abonelik adi" value={subForm.name} onChange={(e) => setSubForm({ ...subForm, name: e.target.value })} required />
                            <input type="number" className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm" placeholder="Tutar" value={subForm.amount} onChange={(e) => setSubForm({ ...subForm, amount: e.target.value })} required />
                            <input type="date" className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm" value={subForm.next_payment_date} onChange={(e) => setSubForm({ ...subForm, next_payment_date: e.target.value })} required />
                            <button type="submit" className="w-full bg-[#135bec] text-white font-bold py-3 rounded-xl">Ekle</button>
                        </form>
                    )}
                </div>

                <div className="lg:col-span-2 space-y-6">
                    {activeTab === 'budget' ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {budgets.length > 0 ? budgets.map((b) => (
                                <div key={b.id} className="bg-white dark:bg-[#101622] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
                                    <div className="flex justify-between items-center">
                                        <p className="font-bold">{b.category_name}</p>
                                        <span className="text-xs font-bold text-slate-500">{new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(b.amount)}</span>
                                    </div>
                                    <p className="text-xs text-slate-500 mt-2">Harcanan: {new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(b.spent || 0)}</p>
                                    <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full mt-2 overflow-hidden">
                                        <div className={`h-full ${b.percentage > 90 ? 'bg-red-500' : 'bg-[#135bec]'}`} style={{ width: `${Math.min(Number(b.percentage || 0), 100)}%` }}></div>
                                    </div>
                                </div>
                            )) : <div className="col-span-2 text-center py-10 bg-slate-50 rounded-2xl border border-dashed border-slate-200">Hedef bulunamadi.</div>}
                        </div>
                    ) : (
                        <div className="bg-white dark:bg-[#101622] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 font-bold text-xs uppercase">
                                    <tr>
                                        <th className="p-4">Platform</th>
                                        <th className="p-4">Tutar</th>
                                        <th className="p-4">Sonraki Odeme</th>
                                        <th className="p-4"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                    {subscriptions.length > 0 ? subscriptions.map((sub) => (
                                        <tr key={sub.id}>
                                            <td className="p-4 font-bold">{sub.name}</td>
                                            <td className="p-4 text-sm font-bold">{new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(sub.amount)}</td>
                                            <td className="p-4 text-sm">{sub.next_payment_date ? new Date(sub.next_payment_date).toLocaleDateString('tr-TR') : '-'}</td>
                                            <td className="p-4 text-right"><button onClick={() => handleDeleteSubscription(sub.id)} className="text-xs bg-red-50 text-red-600 px-2 py-1 rounded">Sil</button></td>
                                        </tr>
                                    )) : <tr><td colSpan="4" className="text-center py-8 text-slate-400 text-sm">Abonelik bulunamadi.</td></tr>}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Planning;
