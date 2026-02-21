import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import { VARIABLE_CATEGORIES } from '../constants/categories';
import { useToast } from '../context/ToastContext';
import ConfirmDialog from '../components/ui/ConfirmDialog';

const Planning = () => {
    const toast = useToast();
    const [activeTab, setActiveTab] = useState('budget');
    const [budgets, setBudgets] = useState([]);
    const [subscriptions, setSubscriptions] = useState([]);
    const [loading, setLoading] = useState(true);

    const [budgetForm, setBudgetForm] = useState({ category_name: 'Market', amount: '' });
    const [subForm, setSubForm] = useState({ name: '', amount: '', next_payment_date: '' });
    const [editingSub, setEditingSub] = useState(null); // null = add, object = edit
    const [deleteTarget, setDeleteTarget] = useState(null); // { type: 'budget'|'subscription', id, label }

    useEffect(() => {
        fetchData();
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const fetchData = async () => {
        try {
            setLoading(true);
            const [bRes, sRes] = await Promise.all([api.getBudgets(), api.getSubscriptions()]);
            setBudgets(bRes.data || []);
            setSubscriptions(sRes.data || []);
        } catch (error) {
            console.error(error);
            toast.show.error('Veriler yüklenemedi');
        } finally {
            setLoading(false);
        }
    };

    /* Budget CRUD */
    const handleBudgetSubmit = async (e) => {
        e.preventDefault();
        if (!budgetForm.amount || parseFloat(budgetForm.amount) <= 0) {
            toast.show.warning('Geçerli bir tutar giriniz');
            return;
        }
        try {
            await api.setBudget({
                category_name: budgetForm.category_name,
                amount: parseFloat(budgetForm.amount)
            });
            toast.show.success('Bütçe hedefi güncellendi');
            setBudgetForm((prev) => ({ ...prev, amount: '' }));
            fetchData();
        } catch (error) {
            toast.show.error('Bütçe güncellenemedi');
        }
    };

    const handleDeleteConfirm = async () => {
        if (!deleteTarget) return;
        try {
            if (deleteTarget.type === 'budget') {
                await api.deleteBudget(deleteTarget.id);
            } else {
                await api.deleteSubscription(deleteTarget.id);
                if (editingSub?.id === deleteTarget.id) resetSubForm();
            }
            toast.show.success(`${deleteTarget.label} silindi`);
            fetchData();
        } catch (error) {
            toast.show.error('Silme başarısız');
        } finally {
            setDeleteTarget(null);
        }
    };

    /* Subscription CRUD */
    const resetSubForm = () => {
        setEditingSub(null);
        setSubForm({ name: '', amount: '', next_payment_date: '' });
    };

    const openEditSub = (sub) => {
        setEditingSub(sub);
        setSubForm({
            name: sub.name || '',
            amount: String(sub.amount || ''),
            next_payment_date: sub.next_payment_date ? sub.next_payment_date.split('T')[0] : ''
        });
        setActiveTab('subscription');
    };

    const handleSubSubmit = async (e) => {
        e.preventDefault();
        if (!subForm.name || !subForm.amount || parseFloat(subForm.amount) <= 0) {
            toast.show.warning('Ad ve geçerli bir tutar giriniz');
            return;
        }

        try {
            if (editingSub) {
                await api.updateSubscription(editingSub.id, {
                    name: subForm.name,
                    amount: parseFloat(subForm.amount),
                    next_payment_date: subForm.next_payment_date || null
                });
                toast.show.success('Abonelik güncellendi');
            } else {
                await api.addSubscription({
                    name: subForm.name,
                    amount: parseFloat(subForm.amount),
                    next_payment_date: subForm.next_payment_date
                });
                toast.show.success('Abonelik eklendi');
            }
            resetSubForm();
            fetchData();
        } catch (error) {
            toast.show.error(editingSub ? 'Güncelleme başarısız' : 'Ekleme başarısız');
        }
    };

    if (loading) {
        return (
            <DashboardLayout>
                <div className="h-56 flex items-center justify-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-500"></div>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <ConfirmDialog
                isOpen={!!deleteTarget}
                title={deleteTarget?.type === 'budget' ? 'Bütçe Hedefini Sil' : 'Aboneliği Sil'}
                message={`"${deleteTarget?.label || ''}" silinecek. Bu işlem geri alınamaz.`}
                confirmText="Evet, Sil"
                onConfirm={handleDeleteConfirm}
                onCancel={() => setDeleteTarget(null)}
                type="danger"
            />

            <div className="mb-8">
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Planlama ve Yönetim</h1>
                <p className="text-slate-500 text-sm">Bütçe hedeflerini ve düzenli ödemeleri yönetin.</p>
            </div>

            <div className="flex gap-4 border-b border-slate-200 dark:border-slate-800 mb-8">
                <button onClick={() => setActiveTab('budget')} className={`pb-3 px-4 text-sm font-bold transition-colors ${activeTab === 'budget' ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}>Bütçe Hedefleri</button>
                <button onClick={() => { setActiveTab('subscription'); if (!editingSub) resetSubForm(); }} className={`pb-3 px-4 text-sm font-bold transition-colors ${activeTab === 'subscription' ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}>Abonelik Takibi</button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Form Panel */}
                <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm h-fit">
                    <h3 className="font-bold text-lg text-slate-900 dark:text-white mb-6 flex items-center gap-2">
                        <span className="material-icons-round text-indigo-600">{activeTab === 'budget' ? 'savings' : (editingSub ? 'edit' : 'add_circle')}</span>
                        {activeTab === 'budget' ? 'Yeni Bütçe Hedefi' : (editingSub ? 'Abonelik Düzenle' : 'Abonelik Ekle')}
                    </h3>

                    {activeTab === 'budget' ? (
                        <form onSubmit={handleBudgetSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Kategori</label>
                                <select className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20" value={budgetForm.category_name} onChange={(e) => setBudgetForm({ ...budgetForm, category_name: e.target.value })}>
                                    {VARIABLE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Aylık Limit (TL)</label>
                                <input type="number" step="0.01" className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3 text-sm font-bold outline-none focus:ring-2 focus:ring-indigo-500/20" placeholder="0.00" value={budgetForm.amount} onChange={(e) => setBudgetForm({ ...budgetForm, amount: e.target.value })} required />
                            </div>
                            <button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-xl transition-colors shadow-lg shadow-indigo-200 dark:shadow-none">Kaydet</button>
                        </form>
                    ) : (
                        <form onSubmit={handleSubSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Abonelik Adı</label>
                                <input type="text" className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20" placeholder="Örn: Netflix, Spotify" value={subForm.name} onChange={(e) => setSubForm({ ...subForm, name: e.target.value })} required />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Tutar (TL)</label>
                                <input type="number" step="0.01" className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3 text-sm font-bold outline-none focus:ring-2 focus:ring-indigo-500/20" placeholder="0.00" value={subForm.amount} onChange={(e) => setSubForm({ ...subForm, amount: e.target.value })} required />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Sonraki Ödeme Tarihi</label>
                                <input type="date" className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20" value={subForm.next_payment_date} onChange={(e) => setSubForm({ ...subForm, next_payment_date: e.target.value })} />
                            </div>
                            <div className="flex gap-3">
                                {editingSub && (
                                    <button
                                        type="button"
                                        onClick={resetSubForm}
                                        className="flex-1 py-3 rounded-xl font-bold text-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors border border-slate-200 dark:border-slate-700"
                                    >
                                        İptal
                                    </button>
                                )}
                                <button type="submit" className={`${editingSub ? 'flex-1' : 'w-full'} bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-xl transition-colors shadow-lg shadow-indigo-200 dark:shadow-none flex items-center justify-center gap-2`}>
                                    <span className="material-icons-round text-sm">{editingSub ? 'check' : 'add'}</span>
                                    {editingSub ? 'Güncelle' : 'Ekle'}
                                </button>
                            </div>
                        </form>
                    )}
                </div>

                {/* Content Panel */}
                <div className="lg:col-span-2 space-y-6">
                    {activeTab === 'budget' ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {budgets.length > 0 ? budgets.map((b) => (
                                <div key={b.id} className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm group hover:shadow-md transition-shadow">
                                    <div className="flex justify-between items-center">
                                        <p className="font-bold text-slate-900 dark:text-white">{b.category_name}</p>
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs font-bold text-slate-500">{new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(b.amount)}</span>
                                            <button onClick={() => setDeleteTarget({ type: 'budget', id: b.id, label: b.category_name })} className="text-slate-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100" title="Sil">
                                                <span className="material-icons-round text-sm">close</span>
                                            </button>
                                        </div>
                                    </div>
                                    <div className="flex justify-between items-center mt-2">
                                        <p className="text-xs text-slate-500">Harcanan: {new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(b.spent || 0)}</p>
                                        <p className={`text-xs font-bold ${(b.percentage || 0) > 90 ? 'text-red-500' : (b.percentage || 0) > 70 ? 'text-amber-500' : 'text-indigo-600'}`}>%{Math.round(b.percentage || 0)}</p>
                                    </div>
                                    <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full mt-2 overflow-hidden">
                                        <div className={`h-full transition-all duration-500 ${(b.percentage || 0) > 90 ? 'bg-red-500' : (b.percentage || 0) > 70 ? 'bg-amber-500' : 'bg-indigo-600'}`} style={{ width: `${Math.min(Number(b.percentage || 0), 100)}%` }}></div>
                                    </div>
                                </div>
                            )) : <div className="col-span-2 text-center py-10 bg-slate-50 dark:bg-slate-900 rounded-2xl border border-dashed border-slate-200 dark:border-slate-700 text-slate-400"><span className="material-icons-round text-3xl opacity-20 block mb-2">savings</span>Hedef bulunamadı.</div>}
                        </div>
                    ) : (
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 font-bold text-xs uppercase">
                                    <tr>
                                        <th className="p-4">Platform</th>
                                        <th className="p-4">Tutar</th>
                                        <th className="p-4">Sonraki Ödeme</th>
                                        <th className="p-4"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                    {subscriptions.length > 0 ? subscriptions.map((sub) => (
                                        <tr key={sub.id} className={`group hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors ${editingSub?.id === sub.id ? 'bg-indigo-50/50 dark:bg-indigo-900/10' : ''}`}>
                                            <td className="p-4 font-bold text-slate-900 dark:text-white">{sub.name}</td>
                                            <td className="p-4 text-sm font-bold">{new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(sub.amount)}</td>
                                            <td className="p-4 text-sm text-slate-600 dark:text-slate-300">{sub.next_payment_date ? new Date(sub.next_payment_date).toLocaleDateString('tr-TR') : '-'}</td>
                                            <td className="p-4 text-right">
                                                <div className="flex items-center gap-1 justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <button onClick={() => openEditSub(sub)} className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 rounded-lg transition-all" title="Düzenle">
                                                        <span className="material-icons-round text-sm">edit</span>
                                                    </button>
                                                    <button onClick={() => setDeleteTarget({ type: 'subscription', id: sub.id, label: sub.name })} className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-all" title="Sil">
                                                        <span className="material-icons-round text-sm">delete</span>
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    )) : <tr><td colSpan="4" className="text-center py-8 text-slate-400 text-sm"><span className="material-icons-round text-3xl opacity-20 block mb-2">subscriptions</span>Abonelik bulunamadı.</td></tr>}
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
