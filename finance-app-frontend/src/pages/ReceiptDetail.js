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

    // Item editing state
    const [editingItemId, setEditingItemId] = useState(null);
    const [editItemForm, setEditItemForm] = useState({});
    const [addingItem, setAddingItem] = useState(false);
    const [newItemForm, setNewItemForm] = useState({ item_name: '', quantity: 1, unit_price: '', total_price: '' });
    const [itemLoading, setItemLoading] = useState(false);
    const [deletingItemId, setDeletingItemId] = useState(null);

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
                category_id: data.category_id || 8,
                payment_method: data.payment_method || 'Kredi Kartı',
                description: data.description || ''
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
            fetchDetail();
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

    // ── Item CRUD ──
    const handleAddItem = async () => {
        if (!newItemForm.item_name.trim()) {
            toast.show.warning('Ürün adı gerekli');
            return;
        }
        try {
            setItemLoading(true);
            await api.addReceiptItem(id, {
                item_name: newItemForm.item_name,
                quantity: Number(newItemForm.quantity) || 1,
                unit_price: Number(newItemForm.unit_price) || 0,
                total_price: Number(newItemForm.total_price) || 0
            });
            toast.show.success('Kalem eklendi');
            setAddingItem(false);
            setNewItemForm({ item_name: '', quantity: 1, unit_price: '', total_price: '' });
            fetchDetail();
        } catch (error) {
            toast.show.error(error.message || 'Kalem eklenemedi');
        } finally {
            setItemLoading(false);
        }
    };

    const startEditItem = (item) => {
        setEditingItemId(item.id);
        setEditItemForm({
            item_name: item.item_name || '',
            quantity: item.quantity || 1,
            unit_price: item.unit_price || 0,
            total_price: item.total_price || 0
        });
    };

    const handleUpdateItem = async (itemId) => {
        try {
            setItemLoading(true);
            await api.updateReceiptItem(id, itemId, editItemForm);
            toast.show.success('Kalem güncellendi');
            setEditingItemId(null);
            fetchDetail();
        } catch (error) {
            toast.show.error(error.message || 'Kalem güncellenemedi');
        } finally {
            setItemLoading(false);
        }
    };

    const handleDeleteItem = async (itemId) => {
        try {
            setItemLoading(true);
            await api.deleteReceiptItem(id, itemId);
            toast.show.success('Kalem silindi');
            setDeletingItemId(null);
            fetchDetail();
        } catch (error) {
            toast.show.error(error.message || 'Kalem silinemedi');
        } finally {
            setItemLoading(false);
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

            {/* Delete item confirm */}
            <ConfirmDialog
                isOpen={!!deletingItemId}
                title="Kalemi Sil"
                message="Bu kalemi silmek istediğinize emin misiniz?"
                confirmText="Sil"
                onConfirm={() => handleDeleteItem(deletingItemId)}
                onCancel={() => setDeletingItemId(null)}
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

                        <div className="grid grid-cols-2 gap-4">
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

                            <div>
                                <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Ödeme Yöntemi</label>
                                <select
                                    value={formData.payment_method}
                                    onChange={(e) => setFormData({ ...formData, payment_method: e.target.value })}
                                    className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none font-medium"
                                >
                                    <option value="Kredi Kartı">Kredi Kartı</option>
                                    <option value="Banka Kartı">Banka Kartı</option>
                                    <option value="Nakit">Nakit</option>
                                    <option value="Havale/EFT">Havale/EFT</option>
                                </select>
                            </div>
                        </div>

                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Açıklama</label>
                            <textarea
                                value={formData.description}
                                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none font-medium min-h-[100px] resize-y"
                                placeholder="Opsiyonel açıklama girin..."
                            />
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

                    {/* Line Items — Editable */}
                    <div className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="font-bold text-lg flex items-center gap-2">
                                <span className="material-icons-round text-accent-green">receipt_long</span>
                                Fiş Kalemleri
                            </h3>
                            <button
                                onClick={() => setAddingItem(!addingItem)}
                                className="text-xs font-bold text-indigo-600 hover:text-indigo-700 flex items-center gap-1 bg-indigo-50 dark:bg-indigo-900/20 px-3 py-1.5 rounded-lg transition-colors"
                            >
                                <span className="material-icons-round text-sm">{addingItem ? 'close' : 'add'}</span>
                                {addingItem ? 'Kapat' : 'Kalem Ekle'}
                            </button>
                        </div>

                        {/* Add new item form */}
                        {addingItem && (
                            <div className="mb-4 p-4 bg-indigo-50 dark:bg-indigo-900/10 rounded-xl border border-indigo-100 dark:border-indigo-800/30 space-y-3">
                                <div>
                                    <label className="text-[10px] font-bold text-slate-500 uppercase block mb-1">Ürün Adı</label>
                                    <input
                                        type="text"
                                        value={newItemForm.item_name}
                                        onChange={(e) => setNewItemForm({ ...newItemForm, item_name: e.target.value })}
                                        placeholder="Ürün adı girin"
                                        className="w-full px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm outline-none focus:ring-2 focus:ring-indigo-200"
                                        autoFocus
                                    />
                                </div>
                                <div className="grid grid-cols-3 gap-2">
                                    <div>
                                        <label className="text-[10px] font-bold text-slate-500 uppercase block mb-1">Adet</label>
                                        <input
                                            type="number" min="1"
                                            value={newItemForm.quantity}
                                            onChange={(e) => setNewItemForm({ ...newItemForm, quantity: e.target.value })}
                                            className="w-full px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm outline-none"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] font-bold text-slate-500 uppercase block mb-1">Birim Fiyat</label>
                                        <input
                                            type="number" step="0.01"
                                            value={newItemForm.unit_price}
                                            onChange={(e) => setNewItemForm({ ...newItemForm, unit_price: e.target.value })}
                                            className="w-full px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm outline-none"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] font-bold text-slate-500 uppercase block mb-1">Toplam</label>
                                        <input
                                            type="number" step="0.01"
                                            value={newItemForm.total_price}
                                            onChange={(e) => setNewItemForm({ ...newItemForm, total_price: e.target.value })}
                                            className="w-full px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm outline-none"
                                        />
                                    </div>
                                </div>
                                <button
                                    onClick={handleAddItem}
                                    disabled={itemLoading}
                                    className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-lg text-sm transition-all disabled:opacity-70 flex items-center justify-center gap-2"
                                >
                                    {itemLoading ? <span className="material-icons-round animate-spin text-sm">refresh</span> : <span className="material-icons-round text-sm">add</span>}
                                    Ekle
                                </button>
                            </div>
                        )}

                        {/* Items list */}
                        <div className="space-y-2">
                            {(receipt?.items || []).map((item) => (
                                <div key={item.id} className="group">
                                    {editingItemId === item.id ? (
                                        /* Edit mode */
                                        <div className="p-3 bg-amber-50 dark:bg-amber-900/10 rounded-xl border border-amber-100 dark:border-amber-800/30 space-y-2">
                                            <input
                                                type="text"
                                                value={editItemForm.item_name}
                                                onChange={(e) => setEditItemForm({ ...editItemForm, item_name: e.target.value })}
                                                className="w-full px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm outline-none font-medium"
                                                autoFocus
                                            />
                                            <div className="grid grid-cols-3 gap-2">
                                                <input
                                                    type="number" min="1"
                                                    value={editItemForm.quantity}
                                                    onChange={(e) => setEditItemForm({ ...editItemForm, quantity: e.target.value })}
                                                    className="px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm outline-none"
                                                    placeholder="Adet"
                                                />
                                                <input
                                                    type="number" step="0.01"
                                                    value={editItemForm.unit_price}
                                                    onChange={(e) => setEditItemForm({ ...editItemForm, unit_price: e.target.value })}
                                                    className="px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm outline-none"
                                                    placeholder="Birim"
                                                />
                                                <input
                                                    type="number" step="0.01"
                                                    value={editItemForm.total_price}
                                                    onChange={(e) => setEditItemForm({ ...editItemForm, total_price: e.target.value })}
                                                    className="px-3 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm outline-none"
                                                    placeholder="Toplam"
                                                />
                                            </div>
                                            <div className="flex gap-2 justify-end">
                                                <button onClick={() => setEditingItemId(null)} className="text-xs font-bold px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-500 hover:bg-slate-50">İptal</button>
                                                <button onClick={() => handleUpdateItem(item.id)} disabled={itemLoading} className="text-xs font-bold px-3 py-1.5 rounded-lg bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-70">Kaydet</button>
                                            </div>
                                        </div>
                                    ) : (
                                        /* View mode */
                                        <div className="flex items-center justify-between py-3 px-3 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/50 border border-transparent hover:border-slate-100 dark:hover:border-slate-700 transition-all">
                                            <div className="flex-1">
                                                <span className="text-sm font-medium text-slate-800 dark:text-slate-200">{item.item_name || 'Ürün'}</span>
                                                {item.quantity > 1 && (
                                                    <span className="ml-2 text-[10px] text-slate-400 font-bold">x{item.quantity}</span>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <span className="font-bold text-slate-900 dark:text-white">{item.total_price} TL</span>
                                                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <button
                                                        onClick={() => startEditItem(item)}
                                                        className="p-1 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 rounded transition-colors"
                                                        title="Düzenle"
                                                    >
                                                        <span className="material-icons-round text-[16px]">edit</span>
                                                    </button>
                                                    <button
                                                        onClick={() => setDeletingItemId(item.id)}
                                                        className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
                                                        title="Sil"
                                                    >
                                                        <span className="material-icons-round text-[16px]">delete_outline</span>
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                            {(!receipt?.items || receipt.items.length === 0) && !addingItem && (
                                <div className="text-center py-8 text-slate-400">
                                    <span className="material-icons-round text-3xl mb-1 opacity-20">list</span>
                                    <p className="text-sm">Kalem bilgisi bulunamadı.</p>
                                    <p className="text-xs mt-1">Yukarıdaki "Kalem Ekle" butonu ile ekleyebilirsiniz.</p>
                                </div>
                            )}
                        </div>

                        {/* Items total */}
                        {receipt?.items && receipt.items.length > 0 && (
                            <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex justify-between items-center">
                                <span className="text-sm font-bold text-slate-500">Kalem Toplamı</span>
                                <span className="text-lg font-bold text-slate-900 dark:text-white">
                                    {receipt.items.reduce((sum, item) => sum + (Number(item.total_price) || 0), 0).toFixed(2)} TL
                                </span>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default ReceiptDetail;
