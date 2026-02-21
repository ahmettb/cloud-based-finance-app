import React, { useState, useEffect } from 'react';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import { VARIABLE_CATEGORIES } from '../constants/categories';
import { useToast } from '../context/ToastContext';
import ConfirmDialog from '../components/ui/ConfirmDialog';

const Planning = () => {
    const toast = useToast();
    const [budgets, setBudgets] = useState([]);
    const [loading, setLoading] = useState(true);

    const [budgetForm, setBudgetForm] = useState({ category_name: 'Market', amount: '' });
    const [deleteTarget, setDeleteTarget] = useState(null); // { id, label }

    useEffect(() => {
        fetchData();
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const fetchData = async () => {
        try {
            setLoading(true);
            const bRes = await api.getBudgets();
            setBudgets(bRes.data || []);
        } catch (error) {
            console.error(error);
            toast.show.error('Bütçe hedefleri yüklenemedi');
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
            await api.deleteBudget(deleteTarget.id);
            toast.show.success(`${deleteTarget.label} bütçesi silindi`);
            fetchData();
        } catch (error) {
            toast.show.error('Silme başarısız');
        } finally {
            setDeleteTarget(null);
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
                title="Bütçe Hedefini Sil"
                message={`"${deleteTarget?.label || ''}" silinecek. Bu işlem geri alınamaz.`}
                confirmText="Evet, Sil"
                onConfirm={handleDeleteConfirm}
                onCancel={() => setDeleteTarget(null)}
                type="danger"
            />

            <div className="mb-8">
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Bütçe Takibi</h1>
                <p className="text-slate-500 text-sm">Kategori bazlı aylık bütçe hedeflerinizi yönetin.</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Form Panel */}
                <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm h-fit">
                    <h3 className="font-bold text-lg text-slate-900 dark:text-white mb-6 flex items-center gap-2">
                        <span className="material-icons-round text-indigo-600">savings</span>
                        Yeni Bütçe Hedefi
                    </h3>

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
                </div>

                {/* Content Panel */}
                <div className="lg:col-span-2 space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {budgets.length > 0 ? budgets.map((b) => (
                            <div key={b.id} className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm group hover:shadow-md transition-shadow">
                                <div className="flex justify-between items-center relative">
                                    <div className="flex flex-col">
                                        <p className="font-bold text-slate-900 dark:text-white">{b.category_name}</p>
                                        <span className="text-xs font-bold text-slate-500 mt-1">{new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(b.amount)} Hedef</span>
                                    </div>
                                    <button onClick={() => setDeleteTarget({ id: b.id, label: b.category_name })} className="absolute -top-1 -right-1 p-2 text-slate-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100" title="Sil">
                                        <span className="material-icons-round text-sm">close</span>
                                    </button>
                                </div>
                                <div className="flex justify-between items-center mt-4">
                                    <p className="text-xs text-slate-500">Harcanan: {new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(b.spent || 0)}</p>
                                    <p className={`text-xs font-bold ${(b.percentage || 0) > 90 ? 'text-red-500' : (b.percentage || 0) > 70 ? 'text-amber-500' : 'text-indigo-600'}`}>%{Math.round(b.percentage || 0)}</p>
                                </div>
                                <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full mt-2 overflow-hidden">
                                    <div className={`h-full transition-all duration-500 ${(b.percentage || 0) > 90 ? 'bg-red-500' : (b.percentage || 0) > 70 ? 'bg-amber-500' : 'bg-indigo-600'}`} style={{ width: `${Math.min(Number(b.percentage || 0), 100)}%` }}></div>
                                </div>
                            </div>
                        )) : <div className="col-span-2 text-center py-10 bg-slate-50 dark:bg-slate-900 rounded-2xl border border-dashed border-slate-200 dark:border-slate-700 text-slate-400"><span className="material-icons-round text-3xl opacity-20 block mb-2">savings</span>Hedef bulunamadı.</div>}
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Planning;
