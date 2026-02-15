import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import DashboardLayout from '../components/layout/DashboardLayout';
import { useToast } from '../context/ToastContext';
import ConfirmDialog from '../components/ui/ConfirmDialog';

const ReceiptDetail = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const toast = useToast();

    const [receipt, setReceipt] = useState(null);
    const [loading, setLoading] = useState(true);
    const [updating, setUpdating] = useState(false);
    const [formData, setFormData] = useState({});
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

    // Categories for dropdown
    const categories = [
        { id: 1, name: 'Market' }, { id: 2, name: 'Restoran' },
        { id: 3, name: 'Kafe' }, { id: 4, name: 'Online Alışveriş' },
        { id: 5, name: 'Fatura' }, { id: 6, name: 'Konaklama' },
        { id: 7, name: 'Ulaşım' }, { id: 8, name: 'Diğer' }
    ];

    const fetchDetail = useCallback(async () => {
        try {
            setLoading(true);
            const data = await api.getReceiptDetail(id);
            setReceipt(data);
            setFormData({
                merchant_name: data.merchant_name || '',
                total_amount: data.total_amount || '',
                receipt_date: data.receipt_date ? data.receipt_date.split('T')[0] : '',
                category_id: data.category_id || 8
            });
        } catch (error) {
            console.error("Detail error:", error);
            toast.show.error("Fiş bulunamadı veya bir hata oluştu.");
            navigate('/receipts');
        } finally {
            setLoading(false);
        }
    }, [id, navigate, toast.show]);

    useEffect(() => {
        fetchDetail();
    }, [fetchDetail]);

    const handleUpdate = async (e) => {
        e.preventDefault();
        try {
            setUpdating(true);
            await api.updateReceipt(id, formData);
            toast.show.success('Güncelleme başarılı!');
            fetchDetail(); // Refresh
        } catch (error) {
            console.error("Update error:", error);
            toast.show.error("Güncelleme başarısız.");
        } finally {
            setUpdating(false);
        }
    };

    const handleDelete = async () => {
        try {
            setLoading(true);
            await api.deleteReceipt(id);
            toast.show.success('Fiş başarıyla silindi');
            navigate('/receipts');
        } catch (error) {
            console.error("Delete error:", error);
            toast.show.error("Silme işlemi başarısız.");
            setLoading(false);
            setShowDeleteConfirm(false);
        }
    };

    if (loading) {
        return (
            <DashboardLayout>
                <div className="flex justify-center items-center h-full">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <ConfirmDialog
                isOpen={showDeleteConfirm}
                title="Fişi Sil"
                message="Bu fişi silmek istediğinize emin misiniz? Bu işlem geri alınamaz."
                confirmText="Evet, Sil"
                onConfirm={handleDelete}
                onCancel={() => setShowDeleteConfirm(false)}
                type="danger"
            />

            <div className="flex items-center justify-between mb-8">
                <button onClick={() => navigate('/receipts')} className="flex items-center gap-2 text-slate-500 hover:text-primary transition-colors font-bold">
                    <span className="material-icons-round">arrow_back</span>
                    Listeye Dön
                </button>
                <button onClick={() => setShowDeleteConfirm(true)} className="bg-red-50 text-red-600 px-4 py-2 rounded-xl text-sm font-bold hover:bg-red-100 transition-colors flex items-center gap-2">
                    <span className="material-icons-round">delete</span>
                    Fişi Sil
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Left: Receipt Update Form */}
                <div className="bg-white dark:bg-slate-900 p-8 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm h-fit">
                    <h2 className="text-xl font-extrabold text-slate-900 dark:text-white mb-6 flex items-center gap-2">
                        <span className="material-icons-round text-primary">edit_note</span>
                        Fiş Bilgileri
                    </h2>

                    <form onSubmit={handleUpdate} className="space-y-5">
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">İşyeri Adı</label>
                            <input
                                type="text"
                                value={formData.merchant_name}
                                onChange={(e) => setFormData({ ...formData, merchant_name: e.target.value })}
                                className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none font-medium"
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Tutar</label>
                                <div className="relative">
                                    <input
                                        type="number" step="0.01"
                                        value={formData.total_amount}
                                        onChange={(e) => setFormData({ ...formData, total_amount: e.target.value })}
                                        className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none font-bold text-lg"
                                    />
                                    <span className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 font-bold">TL</span>
                                </div>
                            </div>

                            <div>
                                <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Tarih</label>
                                <input
                                    type="date"
                                    value={formData.receipt_date}
                                    onChange={(e) => setFormData({ ...formData, receipt_date: e.target.value })}
                                    className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none font-medium text-slate-600"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Kategori</label>
                            <select
                                value={formData.category_id}
                                onChange={(e) => setFormData({ ...formData, category_id: parseInt(e.target.value) })}
                                className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none font-medium"
                            >
                                {categories.map(c => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                            </select>
                        </div>

                        <div className="pt-4">
                            <button
                                type="submit"
                                disabled={updating}
                                className="w-full bg-primary hover:bg-primary-dark text-white font-bold py-3.5 rounded-xl shadow-lg shadow-primary/25 transition-all active:scale-[0.98] disabled:opacity-70 flex items-center justify-center gap-2"
                            >
                                {updating ? <span className="material-icons-round animate-spin">refresh</span> : <span className="material-icons-round">save</span>}
                                {updating ? 'Kaydediliyor...' : 'Değişiklikleri Kaydet'}
                            </button>
                        </div>
                    </form>
                </div>

                {/* Right: Receipt Image & Items */}
                <div className="space-y-6">
                    {/* Image Preview */}
                    <div className="bg-slate-900 rounded-2xl overflow-hidden shadow-lg border border-slate-700 relative group h-96">
                        {receipt?.image_url || receipt?.file_url ? (
                            <img
                                src={receipt?.image_url || receipt?.file_url}
                                alt="Fiş Görseli"
                                className="w-full h-full object-contain bg-black/50"
                            />
                        ) : (
                            <div className="flex items-center justify-center h-full text-slate-500">
                                <p>Görsel Yok</p>
                            </div>
                        )}
                        <a
                            href={receipt?.image_url || receipt?.file_url}
                            target="_blank"
                            rel="noreferrer"
                            className="absolute bottom-4 right-4 bg-white/10 backdrop-blur-md text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-white/20 transition-all flex items-center gap-2"
                        >
                            <span className="material-icons-round">open_in_new</span>
                            Tam Boyut
                        </a>
                    </div>

                    {/* Line Items (if any from Textract) */}
                    {receipt?.items && receipt.items.length > 0 && (
                        <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800">
                            <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                                <span className="material-icons-round text-accent-green">list</span>
                                Algılanan Kalemler
                            </h3>
                            <div className="space-y-3">
                                {receipt.items.map((item, idx) => (
                                    <div key={idx} className="flex justify-between items-center py-2 border-b border-slate-50 dark:border-slate-800 last:border-0">
                                        <span className="text-sm font-medium">{item.item_name || 'Ürün'}</span>
                                        <span className="font-bold text-slate-900 dark:text-white">{item.total_price} TL</span>
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

export default ReceiptDetail;
