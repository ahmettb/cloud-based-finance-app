import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';

const Planning = () => {
    const [activeTab, setActiveTab] = useState('budget'); // 'budget' or 'subscription'
    const [budgets, setBudgets] = useState([]);
    const [subscriptions, setSubscriptions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [message, setMessage] = useState({ type: '', text: '' });

    // Forms
    const [budgetForm, setBudgetForm] = useState({ category_name: 'Market', amount: '' });
    const [subForm, setSubForm] = useState({ name: '', amount: '', next_payment_date: '' });

    // Predefined Categories
    const categories = ['Market', 'Restoran', 'Kafe', 'Ulaşım', 'Fatura', 'Giyim', 'Sağlık', 'Eğlence', 'Teknoloji', 'Diğer'];

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            setLoading(true);
            const [bRes, sRes] = await Promise.all([
                api.getBudgets(),
                api.getSubscriptions()
            ]);
            setBudgets(bRes.data || bRes || []);
            setSubscriptions(sRes.data || sRes || []);
        } catch (error) {
            console.error('Error fetching planning data:', error);
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
            setMessage({ type: 'success', text: 'Bütçe hedefi güncellendi!' });
            fetchData();
            setBudgetForm({ ...budgetForm, amount: '' });
        } catch (error) {
            setMessage({ type: 'error', text: 'Bütçe güncellenemedi.' });
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
            setMessage({ type: 'success', text: 'Abonelik başarıyla eklendi!' });
            fetchData();
            setSubForm({ name: '', amount: '', next_payment_date: '' });
        } catch (error) {
            setMessage({ type: 'error', text: 'Abonelik eklenemedi.' });
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
                <h1 className="text-2xl font-bold text-[#111318] dark:text-white">Planlama & Yönetim</h1>
                <p className="text-slate-500 text-sm">Bütçe hedeflerinizi belirleyin ve düzenli ödemelerinizi takip edin.</p>
            </div>

            {/* Tabs */}
            <div className="flex gap-4 border-b border-slate-200 dark:border-slate-800 mb-8">
                <button
                    onClick={() => setActiveTab('budget')}
                    className={`pb-3 px-4 text-sm font-bold transition-all relative ${activeTab === 'budget' ? 'text-[#135bec] border-b-2 border-[#135bec]' : 'text-slate-500 hover:text-slate-700'}`}
                >
                    Bütçe Hedefleri
                </button>
                <button
                    onClick={() => setActiveTab('subscription')}
                    className={`pb-3 px-4 text-sm font-bold transition-all relative ${activeTab === 'subscription' ? 'text-[#135bec] border-b-2 border-[#135bec]' : 'text-slate-500 hover:text-slate-700'}`}
                >
                    Abonelik Takibi
                </button>
            </div>

            {/* Message Notification */}
            {message.text && (
                <div className={`mb-6 p-4 rounded-xl text-sm font-bold flex items-center gap-2 ${message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                    <span className="material-icons-round">{message.type === 'success' ? 'check_circle' : 'error'}</span>
                    {message.text}
                    <button onClick={() => setMessage({ type: '', text: '' })} className="ml-auto material-icons-round text-sm opacity-50 hover:opacity-100">close</button>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left Column: Form */}
                <div className="bg-white dark:bg-[#101622] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm h-fit">
                    <h3 className="font-bold text-lg text-[#111318] dark:text-white mb-6 flex items-center gap-2">
                        <span className="material-icons-round text-[#135bec]">{activeTab === 'budget' ? 'add_box' : 'playlist_add'}</span>
                        {activeTab === 'budget' ? 'Yeni Hedef Belirle' : 'Abonelik Ekle'}
                    </h3>

                    {activeTab === 'budget' ? (
                        <form onSubmit={handleBudgetSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Kategori</label>
                                <select
                                    className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold text-[#111318] dark:text-white focus:ring-2 focus:ring-[#135bec]"
                                    value={budgetForm.category_name}
                                    onChange={(e) => setBudgetForm({ ...budgetForm, category_name: e.target.value })}
                                >
                                    {categories.map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Aylık Limit (TL)</label>
                                <input
                                    type="number"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold text-[#111318] dark:text-white focus:ring-2 focus:ring-[#135bec]"
                                    placeholder="Örn: 5000"
                                    value={budgetForm.amount}
                                    onChange={(e) => setBudgetForm({ ...budgetForm, amount: e.target.value })}
                                    required
                                />
                            </div>
                            <button type="submit" className="w-full bg-[#135bec] hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-blue-500/30">
                                Kaydet
                            </button>
                        </form>
                    ) : (
                        <form onSubmit={handleSubSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Abonelik Adı</label>
                                <input
                                    type="text"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold text-[#111318] dark:text-white focus:ring-2 focus:ring-[#135bec]"
                                    placeholder="Örn: Netflix, Spotify"
                                    value={subForm.name}
                                    onChange={(e) => setSubForm({ ...subForm, name: e.target.value })}
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Tutar (TL)</label>
                                <input
                                    type="number"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold text-[#111318] dark:text-white focus:ring-2 focus:ring-[#135bec]"
                                    placeholder="0.00"
                                    value={subForm.amount}
                                    onChange={(e) => setSubForm({ ...subForm, amount: e.target.value })}
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Sonraki Ödeme Tarihi</label>
                                <input
                                    type="date"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold text-[#111318] dark:text-white focus:ring-2 focus:ring-[#135bec]"
                                    value={subForm.next_payment_date}
                                    onChange={(e) => setSubForm({ ...subForm, next_payment_date: e.target.value })}
                                    required
                                />
                            </div>
                            <button type="submit" className="w-full bg-[#135bec] hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-blue-500/30">
                                Ekle
                            </button>
                        </form>
                    )}
                </div>

                {/* Right Column: List */}
                <div className="lg:col-span-2 space-y-6">
                    {activeTab === 'budget' ? (
                        <>
                            <h3 className="font-bold text-lg text-[#111318] dark:text-white mb-4">Mevcut Hedefleriniz</h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {budgets.length > 0 ? budgets.map((b, i) => (
                                    <div key={i} className="bg-white dark:bg-[#101622] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md transition-all">
                                        <div className="flex justify-between items-start mb-4">
                                            <div>
                                                <h4 className="font-bold text-[#111318] dark:text-white">{b.category_name}</h4>
                                                <p className="text-xs text-slate-500">Aylık Limit</p>
                                            </div>
                                            <span className="bg-slate-100 text-slate-600 px-2 py-1 rounded text-xs font-bold">
                                                {new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(b.amount)}
                                            </span>
                                        </div>
                                        <div>
                                            <div className="flex justify-between text-xs font-bold mb-1">
                                                <span className={`${b.percentage > 100 ? 'text-red-500' : 'text-[#135bec]'}`}>%{b.percentage}</span>
                                                <span className="text-slate-400">Harcanan: {new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(b.spent)}</span>
                                            </div>
                                            <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                                <div
                                                    className={`h-full rounded-full ${b.percentage > 90 ? 'bg-red-500' : 'bg-[#135bec]'}`}
                                                    style={{ width: `${Math.min(b.percentage, 100)}%` }}
                                                ></div>
                                            </div>
                                        </div>
                                    </div>
                                )) : (
                                    <div className="col-span-2 text-center py-10 bg-slate-50 rounded-2xl border border-dashed border-slate-200">
                                        <p className="text-slate-400 text-sm">Henüz bir bütçe hedefi belirlemediniz.</p>
                                    </div>
                                )}
                            </div>
                        </>
                    ) : (
                        <>
                            <h3 className="font-bold text-lg text-[#111318] dark:text-white mb-4">Aktif Abonelikler</h3>
                            <div className="bg-white dark:bg-[#101622] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                                <table className="w-full text-left border-collapse">
                                    <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 font-bold text-xs uppercase">
                                        <tr>
                                            <th className="p-4">Platform</th>
                                            <th className="p-4">Tutar</th>
                                            <th className="p-4">Sonraki Ödeme</th>
                                            <th className="p-4 text-center">Durum</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                        {subscriptions.length > 0 ? subscriptions.map((sub, i) => (
                                            <tr key={i} className="hover:bg-slate-50 transition-colors">
                                                <td className="p-4 font-bold text-[#111318] dark:text-white flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-600 font-bold">
                                                        {sub.name.charAt(0)}
                                                    </div>
                                                    {sub.name}
                                                </td>
                                                <td className="p-4 text-sm font-bold text-slate-700 dark:text-slate-300">
                                                    {new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(sub.amount)}
                                                </td>
                                                <td className="p-4 text-sm font-medium text-slate-500">
                                                    {new Date(sub.next_payment_date).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })}
                                                </td>
                                                <td className="p-4 text-center">
                                                    <span className="bg-green-100 text-green-700 px-2 py-1 rounded text-xs font-bold">Aktif</span>
                                                </td>
                                            </tr>
                                        )) : (
                                            <tr>
                                                <td colSpan="4" className="text-center py-8 text-slate-400 text-sm">Abonelik bulunamadı.</td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Planning;
