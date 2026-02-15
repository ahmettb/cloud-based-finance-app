import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import DashboardLayout from '../components/layout/DashboardLayout';
import { useToast } from '../context/ToastContext';
import ConfirmDialog from '../components/ui/ConfirmDialog';

const Incomes = () => {
    const toast = useToast();
    const [incomes, setIncomes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [adding, setAdding] = useState(false);
    const [deleteId, setDeleteId] = useState(null);

    const [formData, setFormData] = useState({
        source: '',
        amount: '',
        income_date: new Date().toISOString().split('T')[0],
        description: ''
    });

    useEffect(() => {
        fetchIncomes();
    }, []);

    const fetchIncomes = async () => {
        try {
            setLoading(true);
            const res = await api.getIncomes();
            setIncomes(res.data || []);
        } catch (error) {
            console.error(error);
            toast.show.error('Gelirler yüklenirken hata oluştu');
        } finally {
            setLoading(false);
        }
    };

    const handleAdd = async (e) => {
        e.preventDefault();
        if (!formData.source || !formData.amount) {
            toast.show.warning('Lütfen kaynak ve tutar giriniz');
            return;
        }

        try {
            setAdding(true);
            await api.addIncome(formData);
            toast.show.success('Gelir başarıyla eklendi');
            setFormData({
                source: '',
                amount: '',
                income_date: new Date().toISOString().split('T')[0],
                description: ''
            });
            fetchIncomes();
        } catch (error) {
            console.error(error);
            toast.show.error('Ekleme başarısız');
        } finally {
            setAdding(false);
        }
    };

    const handleDelete = async () => {
        if (!deleteId) return;
        try {
            await api.deleteIncome(deleteId);
            setIncomes(incomes.filter(i => i.id !== deleteId));
            toast.show.success('Gelir silindi');
        } catch (error) {
            toast.show.error('Silme başarısız');
        } finally {
            setDeleteId(null);
        }
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleDateString('tr-TR', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            weekday: 'long'
        });
    };

    const formatCurrency = (amount) => {
        return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(amount);
    };

    return (
        <DashboardLayout>
            <ConfirmDialog
                isOpen={!!deleteId}
                title="Gelir Sil"
                message="Bu geliri silmek istediğinize emin misiniz?"
                confirmText="Evet, Sil"
                onConfirm={handleDelete}
                onCancel={() => setDeleteId(null)}
                type="danger"
            />

            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Gelir Yönetimi</h1>
                    <p className="text-slate-500 text-sm mt-1">Gelir kaynaklarınızı buradan yönetebilirsiniz.</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left: Add Form */}
                <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 h-fit">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                        <span className="material-icons-round text-emerald-600">add_circle</span>
                        Yeni Gelir Ekle
                    </h2>
                    <form onSubmit={handleAdd} className="space-y-4">
                        <div>
                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Gelir Kaynağı</label>
                            <input
                                type="text"
                                placeholder="Örn: Maaş, Freelance, Kira"
                                value={formData.source}
                                onChange={e => setFormData({ ...formData, source: e.target.value })}
                                className="w-full px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-emerald-500/20 text-sm font-medium"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Tutar (TL)</label>
                            <input
                                type="number"
                                placeholder="0.00"
                                value={formData.amount}
                                onChange={e => setFormData({ ...formData, amount: e.target.value })}
                                className="w-full px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-emerald-500/20 text-sm font-bold"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Tarih</label>
                            <input
                                type="date"
                                value={formData.income_date}
                                onChange={e => setFormData({ ...formData, income_date: e.target.value })}
                                className="w-full px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-emerald-500/20 text-sm font-medium text-slate-600"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Açıklama (Opsiyonel)</label>
                            <textarea
                                rows="2"
                                placeholder="Notlar..."
                                value={formData.description}
                                onChange={e => setFormData({ ...formData, description: e.target.value })}
                                className="w-full px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-emerald-500/20 text-sm font-medium resize-none"
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={adding}
                            className="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold py-3 rounded-xl shadow-lg shadow-slate-200 dark:shadow-none transition-all flex justify-center items-center gap-2 disabled:opacity-70"
                        >
                            {adding ? <span className="material-icons-round animate-spin text-sm">refresh</span> : <span className="material-icons-round text-sm">save</span>}
                            {adding ? 'Ekleniyor...' : 'Kaydet'}
                        </button>
                    </form>
                </div>

                {/* Right: List */}
                <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 overflow-hidden flex flex-col min-h-[400px]">
                    <div className="p-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/50 flex justify-between items-center">
                        <h3 className="font-bold text-slate-700 dark:text-slate-300 text-sm">Son Gelirler</h3>
                        <span className="text-xs font-medium text-slate-500">Toplam {incomes.length} kayıt</span>
                    </div>

                    {loading ? (
                        <div className="flex-1 flex items-center justify-center">
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
                        </div>
                    ) : incomes.length === 0 ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-slate-400 p-8">
                            <span className="material-icons-round text-4xl mb-2 opacity-20">savings</span>
                            <p className="text-sm">Henüz gelir kaydı yok.</p>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-slate-50 dark:bg-slate-800/50 text-xs text-slate-500 uppercase border-b border-slate-100 dark:border-slate-800">
                                    <tr>
                                        <th className="p-4 font-bold">Kaynak</th>
                                        <th className="p-4 font-bold">Tarih</th>
                                        <th className="p-4 font-bold text-right">Tutar</th>
                                        <th className="p-4"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                    {incomes.map(inc => (
                                        <tr key={inc.id} className="group hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                                            <td className="p-4">
                                                <div className="font-bold text-slate-900 dark:text-white text-sm">{inc.source}</div>
                                                <div className="text-xs text-slate-400">{inc.description || '-'}</div>
                                            </td>
                                            <td className="p-4 text-sm font-medium text-slate-600 dark:text-slate-300">
                                                {formatDate(inc.income_date)}
                                            </td>
                                            <td className="p-4 text-right">
                                                <span className="font-bold text-emerald-600 dark:text-emerald-400 text-sm">
                                                    +{formatCurrency(inc.amount)}
                                                </span>
                                            </td>
                                            <td className="p-4 text-right">
                                                <button
                                                    onClick={() => setDeleteId(inc.id)}
                                                    className="p-2 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                                                >
                                                    <span className="material-icons-round text-lg">delete</span>
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Incomes;
