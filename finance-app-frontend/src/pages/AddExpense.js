import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';
import { CATEGORY_OPTIONS, CATEGORY_ID_TO_NAME, resolveCategoryId } from '../constants/categories';

const AddExpense = () => {
    const navigate = useNavigate();
    const toast = useToast();
    const fileInputRef = useRef(null);
    const [activeTab, setActiveTab] = useState('manual');
    const [loading, setLoading] = useState(false);
    const [uploadStep, setUploadStep] = useState('idle');
    const [scanResult, setScanResult] = useState(null);

    const [formData, setFormData] = useState({
        merchant: '',
        date: new Date().toISOString().split('T')[0],
        amount: '',
        category: 'Market',
        paymentMethod: 'Kredi Karti',
        description: ''
    });
    const categories = CATEGORY_OPTIONS;

    const paymentMethods = [
        { id: 'credit_card', name: 'Kredi Kartı' },
        { id: 'debit_card', name: 'Banka Kartı' },
        { id: 'cash', name: 'Nakit' },
        { id: 'transfer', name: 'Havale/EFT' }
    ];

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData((prev) => ({ ...prev, [name]: value }));
    };

    const handleFileUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setLoading(true);
        setUploadStep('uploading');

        try {
            const initData = await api.uploadReceipt(file);
            setUploadStep('processing');

            const result = initData.process || {};
            if (result.error) throw new Error(result.error);

            setScanResult(result);
            setUploadStep('done');

            const inferredCategory =
                result.category_name ||
                CATEGORY_ID_TO_NAME[Number(result.category_id)] ||
                'Diger';

            setFormData((prev) => ({
                ...prev,
                merchant: result.merchant_name || '',
                date: result.receipt_date || new Date().toISOString().split('T')[0],
                amount: result.total_amount || '',
                category: inferredCategory,
                description: 'Otomatik fiş tarama ile eklendi'
            }));

            setActiveTab('manual');
        } catch (error) {
            console.error(error);
            toast.show.error(`Fiş okunamadı: ${error.message || 'Bilinmeyen hata'}`);
            setUploadStep('idle');
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);

        try {
            const categoryId = resolveCategoryId(formData.category);

            if (scanResult && scanResult.receipt_id) {
                await api.updateReceipt(scanResult.receipt_id, {
                    merchant_name: formData.merchant,
                    receipt_date: formData.date,
                    total_amount: Number(formData.amount),
                    category_id: categoryId
                });
            } else {
                await api.createManualExpense({
                    merchant_name: formData.merchant,
                    receipt_date: formData.date,
                    total_amount: Number(formData.amount),
                    category_id: categoryId,
                    category_name: formData.category,
                    payment_method: formData.paymentMethod,
                    description: formData.description
                });
            }

            navigate('/');
        } catch (error) {
            toast.show.error(error.message || 'Kaydedilemedi.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <DashboardLayout>
            <div className="max-w-2xl mx-auto">
                <div className="mb-8 flex items-center gap-4">
                    <button
                        onClick={() => navigate(-1)}
                        className="p-2 -ml-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 transition-colors"
                    >
                        <span className="material-icons-round">arrow_back</span>
                    </button>
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Harcama Ekle</h1>
                        <p className="text-slate-500 text-sm">Fiş taratın veya manuel girin.</p>
                    </div>
                </div>

                <div className="flex p-1 bg-slate-100 dark:bg-slate-800 rounded-2xl mb-8">
                    <button
                        onClick={() => setActiveTab('manual')}
                        className={`flex-1 py-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2 ${activeTab === 'manual'
                            ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm'
                            : 'text-slate-500'
                            }`}
                    >
                        <span className="material-icons-round text-sm">edit</span>
                        Manuel
                    </button>
                    <button
                        onClick={() => setActiveTab('scan')}
                        className={`flex-1 py-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2 ${activeTab === 'scan'
                            ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-300 shadow-sm'
                            : 'text-slate-500'
                            }`}
                    >
                        <span className="material-icons-round text-sm">center_focus_strong</span>
                        Fis Tara (AI)
                    </button>
                </div>

                {activeTab === 'scan' && (
                    <div
                        className="bg-white dark:bg-slate-900 rounded-[2rem] p-8 text-center border-2 border-dashed border-slate-200 dark:border-slate-700 hover:border-indigo-400 transition-colors cursor-pointer"
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <input
                            type="file"
                            ref={fileInputRef}
                            className="hidden"
                            accept="image/*,application/pdf"
                            onChange={handleFileUpload}
                        />

                        {loading ? (
                            <div className="py-12">
                                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                                <p className="text-slate-900 dark:text-white font-medium animate-pulse">
                                    {uploadStep === 'uploading' && 'Fiş yükleniyor...'}
                                    {uploadStep === 'processing' && 'AI fişi okuyor...'}
                                </p>
                                <p className="text-xs text-slate-500 mt-2">Bu işlem birkaç saniye sürebilir</p>
                            </div>
                        ) : (
                            <div className="py-12">
                                <div className="w-20 h-20 bg-indigo-50 dark:bg-indigo-900/20 rounded-full flex items-center justify-center mx-auto mb-6 text-indigo-500">
                                    <span className="material-icons-round text-4xl">add_a_photo</span>
                                </div>
                                <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Fişi Buraya Yükleyin</h3>
                                <p className="text-slate-500 mb-6 max-w-xs mx-auto">
                                    Yapay zeka fişi analiz edip form alanlarını otomatik doldurur.
                                </p>
                                <button className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-xl font-bold transition-colors">
                                    Dosya Seç
                                </button>
                            </div>
                        )}
                    </div>
                )}

                {activeTab === 'manual' && (
                    <form
                        onSubmit={handleSubmit}
                        className="bg-white dark:bg-slate-900 rounded-[2rem] p-6 md:p-8 shadow-sm border border-slate-100 dark:border-slate-800 space-y-6"
                    >
                        {scanResult && (
                            <div className="bg-emerald-50 text-emerald-800 p-4 rounded-xl text-sm flex items-center gap-3 mb-6">
                                <span className="material-icons-round">check_circle</span>
                                <div>
                                    <p className="font-bold">Fiş Başarıyla Okundu</p>
                                    <p className="opacity-80 text-xs">Bilgileri kontrol edip kaydedin.</p>
                                </div>
                            </div>
                        )}

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">Mağaza / İşletme</label>
                                <input
                                    type="text"
                                    name="merchant"
                                    required
                                    value={formData.merchant}
                                    onChange={handleChange}
                                    className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border-none focus:ring-2 focus:ring-indigo-500 dark:text-white"
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">Tutar (TL)</label>
                                <input
                                    type="number"
                                    name="amount"
                                    required
                                    step="0.01"
                                    value={formData.amount}
                                    onChange={handleChange}
                                    className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border-none focus:ring-2 focus:ring-indigo-500 dark:text-white font-bold"
                                />
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">Tarih</label>
                                <input
                                    type="date"
                                    name="date"
                                    required
                                    value={formData.date}
                                    onChange={handleChange}
                                    className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border-none focus:ring-2 focus:ring-indigo-500 dark:text-white"
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">Ödeme Yöntemi</label>
                                <select
                                    name="paymentMethod"
                                    value={formData.paymentMethod}
                                    onChange={handleChange}
                                    className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-800 border-none focus:ring-2 focus:ring-indigo-500 dark:text-white"
                                >
                                    {paymentMethods.map((m) => (
                                        <option key={m.id} value={m.name}>
                                            {m.name}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <label className="text-sm font-semibold text-slate-700 dark:text-slate-300">Kategori</label>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                                {categories.map((cat) => (
                                    <button
                                        key={cat.id}
                                        type="button"
                                        onClick={() => setFormData((prev) => ({ ...prev, category: cat.name }))}
                                        className={`flex items-center gap-2 p-3 rounded-xl border text-left text-sm font-medium transition-all ${formData.category === cat.name
                                            ? 'bg-indigo-500 text-white border-indigo-500'
                                            : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'
                                            }`}
                                    >
                                        <span className="material-icons-round text-base">{cat.icon}</span>
                                        {cat.name}
                                    </button>
                                ))}
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full py-4 rounded-xl bg-emerald-600 text-white font-bold hover:bg-emerald-700 transition-all shadow-lg shadow-emerald-200 dark:shadow-none flex justify-center items-center gap-2"
                        >
                            {loading ? 'Kaydediliyor...' : 'Kaydet'}
                        </button>
                    </form>
                )}
            </div>
        </DashboardLayout>
    );
};

export default AddExpense;
