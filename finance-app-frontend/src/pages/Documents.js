import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import DashboardLayout from '../components/layout/DashboardLayout';
import { useNavigate } from 'react-router-dom';
import { useToast } from '../context/ToastContext';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { VARIABLE_CATEGORIES } from '../constants/categories';

const PAGE_SIZE = 20;

const Documents = () => {
    const navigate = useNavigate();
    const toast = useToast();
    const [receipts, setReceipts] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);

    // Server-side pagination
    const [page, setPage] = useState(0); // 0-indexed page
    const [totalCount, setTotalCount] = useState(0);

    // Filters (applied server-side via params)
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('all');
    const [categoryFilter, setCategoryFilter] = useState('all');
    const [dateFilter, setDateFilter] = useState('all');

    // Drawer & Dialogs
    const [selectedReceipt, setSelectedReceipt] = useState(null);
    const [deleteId, setDeleteId] = useState(null);

    // Categories for filter
    const categories = VARIABLE_CATEGORIES;

    const buildParams = useCallback(() => {
        const params = {
            limit: String(PAGE_SIZE),
            offset: String(page * PAGE_SIZE),
        };
        if (statusFilter !== 'all') params.status = statusFilter;

        // Date filter → start_date & end_date
        if (dateFilter !== 'all') {
            const now = new Date();
            let targetMonth, targetYear;
            if (dateFilter === 'this_month') {
                targetMonth = now.getMonth();
                targetYear = now.getFullYear();
            } else if (dateFilter === 'last_month') {
                const last = new Date(now.getFullYear(), now.getMonth() - 1, 1);
                targetMonth = last.getMonth();
                targetYear = last.getFullYear();
            }
            if (targetMonth !== undefined) {
                const startDate = new Date(targetYear, targetMonth, 1);
                const endDate = new Date(targetYear, targetMonth + 1, 0);
                params.start_date = startDate.toISOString().split('T')[0];
                params.end_date = endDate.toISOString().split('T')[0];
            }
        }

        return params;
    }, [page, statusFilter, dateFilter]);

    const fetchReceipts = useCallback(async () => {
        try {
            setLoading(true);
            const params = buildParams();
            const data = await api.getReceipts(params);

            const list = data.data || [];
            // Enrich category field
            setReceipts(list);

            // Extract server-side total
            if (data.pagination && typeof data.pagination.total === 'number') {
                setTotalCount(data.pagination.total);
            } else {
                setTotalCount(list.length);
            }
        } catch (error) {
            console.error(error);
            toast.show.error('Fişler yüklenirken bir hata oluştu');
        } finally {
            setLoading(false);
        }
    }, [buildParams, toast]); // eslint-disable-line react-hooks/exhaustive-deps

    // Re-fetch when filters or page changes
    useEffect(() => {
        fetchReceipts();
    }, [fetchReceipts]);

    // Reset page when filters change
    const handleFilterChange = (setter) => (valueOrEvent) => {
        const value = typeof valueOrEvent === 'object' ? valueOrEvent.target.value : valueOrEvent;
        setter(value);
        setPage(0);
    };

    const handleFileUpload = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        setUploading(true);
        try {
            toast.show.info('Dosya yükleniyor...', 2000);
            await api.uploadReceipt(file);
            toast.show.success('Fiş başarıyla yüklendi ve işleniyor');
            setPage(0);
            await fetchReceipts();
        } catch (error) {
            toast.show.error('Yükleme hatası: ' + error.message);
        } finally {
            setUploading(false);
        }
    };

    const confirmDelete = (id) => {
        setDeleteId(id);
    };

    const handleDelete = async () => {
        if (!deleteId) return;

        try {
            await api.deleteReceipt(deleteId);
            setReceipts(receipts.filter(r => r.id !== deleteId));
            setTotalCount((prev) => Math.max(prev - 1, 0));

            if (selectedReceipt?.id === deleteId) {
                setSelectedReceipt(null);
            }

            toast.show.success('Fiş başarıyla silindi');
        } catch (error) {
            console.error(error);
            toast.show.error('Silme sırasında hata oluştu.');
        } finally {
            setDeleteId(null);
        }
    };

    // Client-side search filter (search within already-fetched page)
    const filteredReceipts = receipts.filter(r => {
        const merchant = (r.merchant_name || '').toLowerCase();
        const search = searchTerm.toLowerCase();
        if (searchTerm && !merchant.includes(search)) return false;

        // Category filter (client-side since backend uses category_id)
        if (categoryFilter !== 'all' && r.category !== categoryFilter) return false;

        return true;
    });

    const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
    const canPrev = page > 0;
    const canNext = (page + 1) * PAGE_SIZE < totalCount;

    const statusConfig = {
        completed: { label: 'Onaylandı', bg: 'bg-green-100', text: 'text-green-700', icon: 'check_circle' },
        pending: { label: 'İnceleniyor', bg: 'bg-amber-100', text: 'text-amber-700', icon: 'hourglass_empty' },
        processing: { label: 'İşleniyor', bg: 'bg-blue-100', text: 'text-blue-700', icon: 'sync' },
        failed: { label: 'Hata', bg: 'bg-red-100', text: 'text-red-700', icon: 'error' }
    };

    const formatCurrency = (amount) => {
        return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(amount || 0);
    };

    return (
        <DashboardLayout>
            <ConfirmDialog
                isOpen={!!deleteId}
                title="Fişi Sil"
                message="Bu fişi silmek istediğinize emin misiniz? Bu işlem geri alınamaz."
                confirmText="Evet, Sil"
                onConfirm={handleDelete}
                onCancel={() => setDeleteId(null)}
                type="danger"
            />

            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
                <div>
                    <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tight leading-tight">Doküman Arşivi</h1>
                    <p className="text-slate-500 dark:text-gray-400 font-medium text-sm mt-1">Tüm harcama belgeleriniz tek bir yerde.</p>
                </div>
                <label className={`cursor-pointer bg-indigo-600 text-white px-5 py-2.5 rounded-xl font-bold text-sm shadow-lg shadow-indigo-200 dark:shadow-none hover:bg-indigo-700 transition-all flex items-center gap-2 ${uploading ? 'opacity-70 cursor-wait' : ''}`}>
                    {uploading ? <span className="material-icons-round animate-spin">refresh</span> : <span className="material-icons-round">cloud_upload</span>}
                    {uploading ? 'Yükleniyor...' : 'Yeni Belge Yükle'}
                    <input type="file" className="hidden" accept="image/jpeg,image/png,application/pdf" onChange={handleFileUpload} disabled={uploading} />
                </label>
            </div>

            {/* Filter Bar */}
            <div className="bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm mb-6 grid grid-cols-1 md:grid-cols-4 gap-4">
                {/* Search */}
                <div className="relative md:col-span-1">
                    <span className="material-icons-round absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-[20px]">search</span>
                    <input
                        type="text"
                        placeholder="Mağaza veya açıklama ara..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium text-slate-700 dark:text-white focus:ring-2 focus:ring-indigo-500/20 outline-none"
                    />
                </div>

                {/* Date Filter */}
                <div className="flex items-center bg-slate-50 dark:bg-slate-800 rounded-xl p-1 md:col-span-1 border border-slate-200 dark:border-slate-700">
                    <button onClick={() => handleFilterChange(setDateFilter)('all')} className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-colors ${dateFilter === 'all' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Tümü</button>
                    <button onClick={() => handleFilterChange(setDateFilter)('this_month')} className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-colors ${dateFilter === 'this_month' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Bu Ay</button>
                    <button onClick={() => handleFilterChange(setDateFilter)('last_month')} className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-colors ${dateFilter === 'last_month' ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>Geçen Ay</button>
                </div>

                {/* Category Filter */}
                <select
                    value={categoryFilter}
                    onChange={handleFilterChange(setCategoryFilter)}
                    className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium text-slate-700 dark:text-white focus:ring-2 focus:ring-indigo-500/20 outline-none md:col-span-1 cursor-pointer appearance-none"
                >
                    <option value="all">Tüm Kategoriler</option>
                    {categories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>

                {/* Status Filter */}
                <select
                    value={statusFilter}
                    onChange={handleFilterChange(setStatusFilter)}
                    className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium text-slate-700 dark:text-white focus:ring-2 focus:ring-indigo-500/20 outline-none md:col-span-1 cursor-pointer appearance-none"
                >
                    <option value="all">Tüm Durumlar</option>
                    <option value="completed">Onaylananlar</option>
                    <option value="pending">İncelenenler</option>
                    <option value="failed">Hatalı</option>
                </select>
            </div>

            {/* Table */}
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden flex flex-col min-h-[400px]">
                {loading ? (
                    <div className="flex-1 flex items-center justify-center">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
                    </div>
                ) : filteredReceipts.length === 0 ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-400 p-10">
                        <span className="material-icons-round text-5xl opacity-20 mb-3">folder_open</span>
                        <p>Kayıt bulunamadı.</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse">
                            <thead className="bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800">
                                <tr>
                                    <th className="p-4 pl-6 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Mağaza</th>
                                    <th className="p-4 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Tarih</th>
                                    <th className="p-4 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Kategori</th>
                                    <th className="p-4 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-right">Tutar</th>
                                    <th className="p-4 text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Durum</th>
                                    <th className="p-4 pr-6"></th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                {filteredReceipts.map(r => (
                                    <tr
                                        key={r.id}
                                        onClick={() => setSelectedReceipt(r)}
                                        className={`group cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50 ${selectedReceipt?.id === r.id ? 'bg-indigo-50/50 dark:bg-indigo-900/10' : ''}`}
                                    >
                                        <td className="p-4 pl-6">
                                            <div className="flex items-center gap-3">
                                                <div className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-500 font-bold overflow-hidden border border-slate-200 dark:border-slate-700">
                                                    {r.image_url ? (
                                                        <img src={r.image_url} alt="" className="w-full h-full object-cover opacity-80" />
                                                    ) : (
                                                        <span className="material-icons-round text-lg opacity-50">receipt</span>
                                                    )}
                                                </div>
                                                <div>
                                                    <p className="font-bold text-slate-900 dark:text-white text-sm">{r.merchant_name || 'Bilinmeyen Mağaza'}</p>
                                                    <p className="text-[10px] text-slate-400 uppercase tracking-wide font-medium">{r.id.slice(0, 8)}</p>
                                                </div>
                                            </div>
                                        </td>
                                        <td className="p-4 text-sm font-medium text-slate-600 dark:text-slate-300">
                                            {new Date(r.receipt_date || r.date).toLocaleDateString('tr-TR')}
                                        </td>
                                        <td className="p-4">
                                            <span className="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                                                {r.category || 'Diğer'}
                                            </span>
                                        </td>
                                        <td className="p-4 text-right">
                                            <span className="font-bold text-slate-900 dark:text-white block">
                                                {formatCurrency(r.total_amount || r.amount)}
                                            </span>
                                        </td>
                                        <td className="p-4">
                                            <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold border ${statusConfig[r.status]?.bg || 'bg-gray-100'} ${statusConfig[r.status]?.text || 'text-gray-600'} border-transparent`}>
                                                <span className="material-icons-round text-[14px]">{statusConfig[r.status]?.icon || 'help'}</span>
                                                {statusConfig[r.status]?.label || r.status}
                                            </div>
                                        </td>
                                        <td className="p-4 pr-6 text-right">
                                            <button className="text-slate-300 hover:text-indigo-600 p-1 rounded-full transition-colors">
                                                <span className="material-icons-round">chevron_right</span>
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Server-side Pagination Controls */}
                <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30 flex justify-between items-center">
                    <p className="text-xs font-medium text-slate-500">
                        {totalCount > 0
                            ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, totalCount)} / ${totalCount} kayıt`
                            : 'Kayıt yok'}
                    </p>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setPage(p => Math.max(0, p - 1))}
                            disabled={!canPrev}
                            className="px-3 py-1.5 rounded-lg text-xs font-bold border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                        >
                            <span className="material-icons-round text-sm">chevron_left</span>
                            Önceki
                        </button>
                        <span className="text-xs font-bold text-slate-500">
                            {page + 1} / {totalPages}
                        </span>
                        <button
                            onClick={() => setPage(p => p + 1)}
                            disabled={!canNext}
                            className="px-3 py-1.5 rounded-lg text-xs font-bold border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                        >
                            Sonraki
                            <span className="material-icons-round text-sm">chevron_right</span>
                        </button>
                    </div>
                </div>
            </div>

            {/* Quick View Drawer */}
            {selectedReceipt && (
                <div className="fixed inset-y-0 right-0 w-[450px] bg-white dark:bg-slate-900 shadow-[0_0_50px_rgba(0,0,0,0.2)] z-40 transform transition-transform animate-slide-in-right flex flex-col border-l border-slate-200 dark:border-slate-800">
                    {/* Drawer Header */}
                    <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-800/50">
                        <div className="flex items-center gap-3">
                            <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-white shadow-sm ${statusConfig[selectedReceipt.status]?.bg?.replace('100', '500') || 'bg-gray-500'}`}>
                                <span className="material-icons-round text-lg">receipt_long</span>
                            </div>
                            <div>
                                <h3 className="font-bold text-slate-900 dark:text-white">Fiş Detayı</h3>
                                <p className="text-xs text-slate-500 font-mono">{selectedReceipt.id}</p>
                            </div>
                        </div>
                        <button onClick={() => setSelectedReceipt(null)} className="w-8 h-8 flex items-center justify-center rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-700 hover:shadow-sm transition-all">
                            <span className="material-icons-round text-sm">close</span>
                        </button>
                    </div>

                    {/* Scrollable Content */}
                    <div className="flex-1 overflow-y-auto p-6 space-y-6">
                        {/* Status Alert */}
                        {selectedReceipt.status === 'failed' && (
                            <div className="bg-red-50 text-red-700 p-4 rounded-xl text-sm font-medium border border-red-100 flex items-start gap-3">
                                <span className="material-icons-round mt-0.5">error</span>
                                <div>
                                    <p className="font-bold">İşlem Başarısız</p>
                                    <p className="opacity-80 mt-1">Bu fiş işlenirken bir sorun oluştu. Lütfen tekrar yükleyin veya manuel düzenleyin.</p>
                                </div>
                            </div>
                        )}

                        {/* Image Preview */}
                        <div className="aspect-[3/4] bg-slate-100 dark:bg-slate-800 rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700 relative group shadow-inner flex items-center justify-center">
                            {selectedReceipt.image_url ? (
                                <img src={selectedReceipt.image_url} alt="Receipt" className="max-w-full max-h-full object-contain" />
                            ) : (
                                <div className="text-slate-400 text-center">
                                    <span className="material-icons-round text-4xl opacity-30 block mb-2">image_not_supported</span>
                                    <span className="text-sm">Görsel yok</span>
                                </div>
                            )}
                            {selectedReceipt.image_url && (
                                <a
                                    href={selectedReceipt.image_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="absolute bottom-4 right-4 bg-white/90 dark:bg-slate-900/90 backdrop-blur text-slate-900 dark:text-white px-3 py-1.5 rounded-lg text-xs font-bold shadow-lg flex items-center gap-2 hover:scale-105 transition-all opacity-0 group-hover:opacity-100"
                                >
                                    <span className="material-icons-round text-sm">visibility</span>
                                    Tam Ekran
                                </a>
                            )}
                        </div>

                        {/* Key Value Pairs */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-800/50">
                                <span className="text-xs font-bold text-slate-400 uppercase block mb-1">Tarih</span>
                                <p className="font-bold text-slate-900 dark:text-white">{new Date(selectedReceipt.receipt_date || selectedReceipt.date).toLocaleDateString('tr-TR')}</p>
                            </div>
                            <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-800/50">
                                <span className="text-xs font-bold text-slate-400 uppercase block mb-1">Tutar</span>
                                <p className="font-bold text-slate-900 dark:text-white">{formatCurrency(selectedReceipt.total_amount || selectedReceipt.amount)}</p>
                            </div>
                        </div>

                        {/* Merchant & Category */}
                        <div>
                            <label className="text-xs font-bold text-slate-400 uppercase block mb-2">Mağaza Bilgisi</label>
                            <div className="flex items-center gap-3 p-3 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
                                <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-900/20 text-indigo-600 flex items-center justify-center">
                                    <span className="material-icons-round">store</span>
                                </div>
                                <div className="flex-1">
                                    <p className="font-bold text-slate-900 dark:text-white">{selectedReceipt.merchant_name || 'Bilinmiyor'}</p>
                                    <p className="text-xs text-slate-500">{selectedReceipt.merchant_address || 'Adres yok'}</p>
                                </div>
                            </div>
                        </div>

                        {/* Actions */}
                        <div className="grid grid-cols-2 gap-3 pt-4 border-t border-slate-200 dark:border-slate-800">
                            <button
                                onClick={() => navigate(`/receipts/${selectedReceipt.id}`)}
                                className="flex items-center justify-center gap-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 py-3 rounded-xl font-bold text-sm text-slate-900 dark:text-white hover:bg-slate-50 transition-colors"
                            >
                                <span className="material-icons-round text-sm">edit</span>
                                Düzenle
                            </button>
                            <button
                                onClick={() => confirmDelete(selectedReceipt.id)}
                                className="flex items-center justify-center gap-2 bg-red-50 dark:bg-red-900/20 py-3 rounded-xl font-bold text-sm text-red-600 hover:bg-red-100 transition-colors"
                            >
                                <span className="material-icons-round text-sm">delete</span>
                                Sil
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </DashboardLayout>
    );
};

export default Documents;
