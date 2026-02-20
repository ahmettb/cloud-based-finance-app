import React, { useState } from 'react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';
import { CATEGORY_OPTIONS, resolveCategoryId } from '../constants/categories';

const CATEGORIES = CATEGORY_OPTIONS.map((item) => item.name);

const ManualExpenseModal = ({ isOpen, onClose, onSave }) => {
    const toast = useToast();
    const [loading, setLoading] = useState(false);
    const [formData, setFormData] = useState({
        merchant_name: '',
        total_amount: '',
        receipt_date: new Date().toISOString().split('T')[0],
        category_name: 'Diger',
        description: ''
    });

    if (!isOpen) return null;

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);

        if (!formData.merchant_name || !formData.total_amount) {
            toast.show.warning('Lutfen satici adi ve tutar giriniz.');
            setLoading(false);
            return;
        }

        try {
            await api.createManualExpense({
                ...formData,
                total_amount: parseFloat(formData.total_amount),
                category_id: resolveCategoryId(formData.category_name)
            });
            toast.show.success('Harcama basariyla eklendi.');
            onSave();
            onClose();
            setFormData({
                merchant_name: '',
                total_amount: '',
                receipt_date: new Date().toISOString().split('T')[0],
                category_name: 'Diger',
                description: ''
            });
        } catch (error) {
            console.error(error);
            toast.show.error('Ekleme basarisiz oldu.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
            <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-md border border-slate-200 dark:border-slate-800 overflow-hidden animate-in fade-in zoom-in duration-200">
                <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-800/50">
                    <h3 className="font-bold text-slate-800 dark:text-white flex items-center gap-2">
                        <span className="material-icons-round text-indigo-500">receipt_long</span>
                        Manuel Harcama Ekle
                    </h3>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
                        <span className="material-icons-round">close</span>
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Satici / Yer</label>
                        <input
                            type="text"
                            placeholder="Orn: Migros"
                            value={formData.merchant_name}
                            onChange={(e) => setFormData({ ...formData, merchant_name: e.target.value })}
                            className="w-full px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm font-medium"
                            autoFocus
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Tutar (TL)</label>
                            <input
                                type="number"
                                placeholder="0.00"
                                step="0.01"
                                value={formData.total_amount}
                                onChange={(e) => setFormData({ ...formData, total_amount: e.target.value })}
                                className="w-full px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm font-bold"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Tarih</label>
                            <input
                                type="date"
                                value={formData.receipt_date}
                                onChange={(e) => setFormData({ ...formData, receipt_date: e.target.value })}
                                className="w-full px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Kategori</label>
                        <div className="grid grid-cols-3 gap-2">
                            {CATEGORIES.map((cat) => (
                                <button
                                    key={cat}
                                    type="button"
                                    onClick={() => setFormData({ ...formData, category_name: cat })}
                                    className={`px-2 py-2 text-[10px] font-bold rounded-lg border transition-all truncate ${
                                        formData.category_name === cat
                                            ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
                                            : 'bg-white border-slate-100 text-slate-500 hover:border-slate-300'
                                    }`}
                                >
                                    {cat}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Aciklama</label>
                        <textarea
                            rows="2"
                            placeholder="Detaylar..."
                            value={formData.description}
                            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                            className="w-full px-4 py-2 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm resize-none"
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold py-3 rounded-xl transition-all flex justify-center items-center gap-2 disabled:opacity-70 mt-2"
                    >
                        {loading ? <span className="material-icons-round animate-spin text-sm">refresh</span> : <span className="material-icons-round text-sm">save</span>}
                        {loading ? 'Kaydediliyor...' : 'Kaydet'}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default ManualExpenseModal;
