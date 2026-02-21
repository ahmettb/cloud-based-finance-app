import os

content = """import React, { useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import DashboardLayout from '../components/layout/DashboardLayout';
import { useToast } from '../context/ToastContext';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import { FIXED_GROUP_CATEGORIES } from '../constants/categories';

/* helpers */
const fmtCurrency = (v) =>
    new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(v || 0);

const fmtMonth = (iso) => {
    const [y, m] = iso.split('-');
    const months = ['Ocak', '\u015eubat', 'Mart', 'Nisan', 'May\u0131s', 'Haziran', 'Temmuz', 'A\u011fustos', 'Eyl\u00fcl', 'Ekim', 'Kas\u0131m', 'Aral\u0131k'];
    return `${months[parseInt(m, 10) - 1]} ${y}`;
};

const shiftMonth = (iso, dir) => {
    const d = new Date(iso + '-01');
    d.setMonth(d.getMonth() + dir);
    return d.toISOString().slice(0, 7);
};

const STATUS_BADGE = {
    paid: { label: '\u00d6dendi', color: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400', icon: 'check_circle' },
    pending: { label: 'Bekliyor', color: 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400', icon: 'schedule' },
    overdue: { label: 'Gecikmi\u015f', color: 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400', icon: 'error' },
};

const CATEGORY_ICONS = {
    Kira: 'home',
    Fatura: 'receipt_long',
    Abonelik: 'subscriptions',
    Kredi: 'credit_card',
    'E\u011fitim': 'school',
    'Di\u011fer': 'more_horiz',
};

/* component */
const Expenses = () => {
    const toast = useToast();

    /* state */
    const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
    const [groups, setGroups] = useState([]);
    const [stats, setStats] = useState({ total: 0, paid: 0, remaining: 0, count: 0, pending_count: 0 });
    const [loading, setLoading] = useState(true);

    /* dialogs */
    const [showGroupForm, setShowGroupForm] = useState(false);
    const [showItemForm, setShowItemForm] = useState(null);
    const [editGroup, setEditGroup] = useState(null);
    const [editItem, setEditItem] = useState(null);
    const [deleteTarget, setDeleteTarget] = useState(null);

    /* forms */
    const [groupForm, setGroupForm] = useState({ title: '', category_type: FIXED_GROUP_CATEGORIES[0] });
    const [itemForm, setItemForm] = useState({ name: '', amount: '', day: '1' });

    /* fetch */
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { fetchData(); }, [month]);

    const fetchData = async () => {
        try {
            setLoading(true);
            const res = await api.getFixedExpenses(month);
            setGroups(res.data || []);
            setStats(res.stats || { total: 0, paid: 0, remaining: 0, count: 0, pending_count: 0 });
        } catch (err) {
            toast.show.error('Sabit giderler y\u00fcklenemedi');
        } finally {
            setLoading(false);
        }
    };

    /* group CRUD */
    const handleGroupSubmit = async (e) => {
        e.preventDefault();
        const title = groupForm.title.trim();
        if (!title) { toast.show.warning('Grup ad\u0131 gerekli'); return; }

        try {
            if (editGroup) {
                await api.updateFixedExpenseGroup(editGroup.id, groupForm);
                toast.show.success('Grup g\u00fcncellendi');
            } else {
                await api.createFixedExpenseGroup(groupForm);
                toast.show.success('Yeni grup olu\u015fturuldu');
            }
            resetGroupForm();
            fetchData();
        } catch {
            toast.show.error(editGroup ? 'G\u00fcncelleme ba\u015far\u0131s\u0131z' : 'Olu\u015fturma ba\u015far\u0131s\u0131z');
        }
    };

    const resetGroupForm = () => {
        setShowGroupForm(false);
        setEditGroup(null);
        setGroupForm({ title: '', category_type: FIXED_GROUP_CATEGORIES[0] });
    };

    const openEditGroup = (g) => {
        setEditGroup(g);
        setGroupForm({ title: g.title, category_type: g.category_type || FIXED_GROUP_CATEGORIES[0] });
        setShowGroupForm(true);
    };

    /* item CRUD */
    const handleItemSubmit = async (e) => {
        e.preventDefault();
        const name = itemForm.name.trim();
        const amount = parseFloat(itemForm.amount);
        const day = parseInt(itemForm.day, 10);

        if (!name || isNaN(amount) || amount <= 0) { toast.show.warning('Ad ve ge\u00e7erli bir tutar giriniz'); return; }
        if (isNaN(day) || day < 1 || day > 31) { toast.show.warning('G\u00fcn 1-31 aras\u0131nda olmal\u0131'); return; }

        try {
            if (editItem) {
                await api.updateFixedExpenseItem(editItem.id, { name, amount, day });
                toast.show.success('Kalem g\u00fcncellendi');
            } else {
                await api.addFixedExpenseItem({ group_id: showItemForm, name, amount, day });
                toast.show.success('Kalem eklendi');
            }
            resetItemForm();
            fetchData();
        } catch {
            toast.show.error('\u0130\u015flem ba\u015far\u0131s\u0131z');
        }
    };

    const resetItemForm = () => {
        setShowItemForm(null);
        setEditItem(null);
        setItemForm({ name: '', amount: '', day: '1' });
    };

    const openEditItem = (item, groupId) => {
        setEditItem(item);
        setShowItemForm(groupId);
        setItemForm({ name: item.name, amount: String(item.amount), day: String(item.day) });
    };

    /* payment toggle */
    const handlePaymentToggle = async (item) => {
        const newStatus = item.status === 'paid' ? 'pending' : 'paid';
        try {
            await api.saveFixedExpensePayment(item.id, { status: newStatus, month });
            fetchData();
            toast.show.success(newStatus === 'paid' ? '\u00d6dendi olarak i\u015faretlendi' : 'Bekliyora \u00e7evrildi');
        } catch {
            toast.show.error('Durum g\u00fcncellenemedi');
        }
    };

    /* delete */
    const handleDeleteConfirm = async () => {
        if (!deleteTarget) return;
        try {
            if (deleteTarget.type === 'group') {
                await api.deleteFixedExpenseGroup(deleteTarget.id);
            } else {
                await api.deleteFixedExpenseItem(deleteTarget.id);
            }
            toast.show.success(`${deleteTarget.label} silindi`);
            fetchData();
        } catch {
            toast.show.error('Silme ba\u015far\u0131s\u0131z');
        } finally {
            setDeleteTarget(null);
        }
    };

    /* derived */
    const paidPct = useMemo(() => (stats.total > 0 ? Math.round((stats.paid / stats.total) * 100) : 0), [stats]);
    const isCurrentMonth = month === new Date().toISOString().slice(0, 7);

    /* render */
    if (loading) {
        return (
            <DashboardLayout>
                <div className="flex items-center justify-center min-h-[400px]">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-500"></div>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <ConfirmDialog
                isOpen={!!deleteTarget}
                title={deleteTarget?.type === 'group' ? 'Grubu Sil' : 'Kalemi Sil'}
                message={`"${deleteTarget?.label || ''}" silinecek. Bu i\u015flem geri al\u0131namaz.`}
                confirmText="Evet, Sil"
                onConfirm={handleDeleteConfirm}
                onCancel={() => setDeleteTarget(null)}
                type="danger"
            />

            {/* Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Gider Y\u00f6netimi</h1>
                    <p className="text-slate-500 text-sm mt-1">Sabit giderlerinizi gruplar halinde takip edin.</p>
                </div>
                <button
                    onClick={() => { resetGroupForm(); setShowGroupForm(true); }}
                    className="bg-slate-900 dark:bg-indigo-600 hover:bg-slate-800 dark:hover:bg-indigo-700 text-white px-4 py-2.5 rounded-xl flex items-center gap-2 font-bold text-sm shadow-lg shadow-slate-200 dark:shadow-none transition-all"
                >
                    <span className="material-icons-round text-lg">add</span>
                    Yeni Grup
                </button>
            </div>

            {/* Month Nav */}
            <div className="flex items-center justify-between mb-6 bg-white dark:bg-slate-900 p-4 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800">
                <button onClick={() => setMonth(shiftMonth(month, -1))} className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                    <span className="material-icons-round text-slate-600 dark:text-slate-400">chevron_left</span>
                </button>
                <div className="text-center">
                    <h2 className="text-lg font-bold text-slate-900 dark:text-white">{fmtMonth(month)}</h2>
                    {isCurrentMonth && <span className="text-xs text-indigo-600 font-medium">Bu Ay</span>}
                </div>
                <button onClick={() => setMonth(shiftMonth(month, 1))} className="p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
                    <span className="material-icons-round text-slate-600 dark:text-slate-400">chevron_right</span>
                </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
                    <p className="text-[10px] font-bold text-slate-500 uppercase mb-1">Toplam Gider</p>
                    <p className="text-xl font-bold text-slate-900 dark:text-white">{fmtCurrency(stats.total)}</p>
                </div>
                <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
                    <p className="text-[10px] font-bold text-emerald-600 uppercase mb-1">\u00d6denen</p>
                    <p className="text-xl font-bold text-emerald-600">{fmtCurrency(stats.paid)}</p>
                </div>
                <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
                    <p className="text-[10px] font-bold text-amber-600 uppercase mb-1">Kalan</p>
                    <p className="text-xl font-bold text-amber-600">{fmtCurrency(stats.remaining)}</p>
                </div>
                <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
                    <p className="text-[10px] font-bold text-slate-500 uppercase mb-1">Tamamlanma</p>
                    <div className="flex items-center gap-2">
                        <p className="text-xl font-bold text-slate-900 dark:text-white">%{paidPct}</p>
                        <div className="flex-1 h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-500 rounded-full transition-all duration-500" style={{ width: `${paidPct}%` }}></div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Group Form Dialog */}
            {showGroupForm && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in" onClick={() => resetGroupForm()}>
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-md w-full shadow-2xl border border-slate-100 dark:border-slate-800 animate-scale-in" onClick={e => e.stopPropagation()}>
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                            <span className="material-icons-round text-indigo-600">{editGroup ? 'edit' : 'create_new_folder'}</span>
                            {editGroup ? 'Grubu D\u00fczenle' : 'Yeni Gider Grubu'}
                        </h3>
                        <form onSubmit={handleGroupSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Grup Ad\u0131</label>
                                <input
                                    autoFocus
                                    type="text"
                                    placeholder="\u00d6rn: Ev Giderleri"
                                    value={groupForm.title}
                                    onChange={e => setGroupForm({ ...groupForm, title: e.target.value })}
                                    className="w-full px-4 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm font-medium"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Kategori</label>
                                <select
                                    value={groupForm.category_type}
                                    onChange={e => setGroupForm({ ...groupForm, category_type: e.target.value })}
                                    className="w-full px-4 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm font-medium"
                                >
                                    {FIXED_GROUP_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </div>
                            <div className="flex gap-3 pt-2">
                                <button type="button" onClick={resetGroupForm} className="flex-1 py-2.5 rounded-xl font-bold text-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
                                    \u0130ptal
                                </button>
                                <button type="submit" className="flex-1 py-2.5 rounded-xl font-bold bg-slate-900 dark:bg-indigo-600 text-white hover:bg-slate-800 dark:hover:bg-indigo-700 transition-colors shadow-lg">
                                    {editGroup ? 'G\u00fcncelle' : 'Olu\u015ftur'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Item Form Dialog */}
            {showItemForm && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in" onClick={() => resetItemForm()}>
                    <div className="bg-white dark:bg-slate-900 rounded-2xl p-6 max-w-md w-full shadow-2xl border border-slate-100 dark:border-slate-800 animate-scale-in" onClick={e => e.stopPropagation()}>
                        <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
                            <span className="material-icons-round text-indigo-600">{editItem ? 'edit' : 'add_circle'}</span>
                            {editItem ? 'Kalemi D\u00fczenle' : 'Yeni Gider Kalemi'}
                        </h3>
                        <form onSubmit={handleItemSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Kalem Ad\u0131</label>
                                <input
                                    autoFocus
                                    type="text"
                                    placeholder="\u00d6rn: Elektrik Faturas\u0131"
                                    value={itemForm.name}
                                    onChange={e => setItemForm({ ...itemForm, name: e.target.value })}
                                    className="w-full px-4 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm font-medium"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Tutar (TL)</label>
                                    <input
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        placeholder="0.00"
                                        value={itemForm.amount}
                                        onChange={e => setItemForm({ ...itemForm, amount: e.target.value })}
                                        className="w-full px-4 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm font-bold"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 uppercase mb-1">\u00d6deme G\u00fcn\u00fc</label>
                                    <input
                                        type="number"
                                        min="1"
                                        max="31"
                                        value={itemForm.day}
                                        onChange={e => setItemForm({ ...itemForm, day: e.target.value })}
                                        className="w-full px-4 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-indigo-500/20 text-sm font-medium"
                                    />
                                </div>
                            </div>
                            <div className="flex gap-3 pt-2">
                                <button type="button" onClick={resetItemForm} className="flex-1 py-2.5 rounded-xl font-bold text-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
                                    \u0130ptal
                                </button>
                                <button type="submit" className="flex-1 py-2.5 rounded-xl font-bold bg-slate-900 dark:bg-indigo-600 text-white hover:bg-slate-800 dark:hover:bg-indigo-700 transition-colors shadow-lg">
                                    {editItem ? 'G\u00fcncelle' : 'Ekle'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Groups & Items */}
            {groups.length === 0 ? (
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm p-12 flex flex-col items-center text-center">
                    <span className="material-icons-round text-5xl text-slate-200 dark:text-slate-700 mb-4">account_balance</span>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">Hen\u00fcz sabit gider grubu yok</h3>
                    <p className="text-sm text-slate-500 mb-6 max-w-sm">Kira, fatura ve abonelik gibi d\u00fczenli giderlerinizi gruplar halinde takip etmeye ba\u015flay\u0131n.</p>
                    <button
                        onClick={() => { resetGroupForm(); setShowGroupForm(true); }}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-xl font-bold text-sm transition-all flex items-center gap-2 shadow-lg shadow-indigo-200 dark:shadow-none"
                    >
                        <span className="material-icons-round text-lg">add</span>
                        \u0130lk Grubu Olu\u015ftur
                    </button>
                </div>
            ) : (
                <div className="space-y-6">
                    {groups.map(group => {
                        const groupPaid = (group.items || []).filter(i => i.status === 'paid').length;
                        const groupTotal = (group.items || []).length;
                        const catIcon = CATEGORY_ICONS[group.category_type] || 'folder';

                        return (
                            <div key={group.id} className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                                {/* Group Header */}
                                <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-900/30 flex items-center justify-center flex-shrink-0">
                                            <span className="material-icons-round text-indigo-600 dark:text-indigo-400">{catIcon}</span>
                                        </div>
                                        <div className="min-w-0">
                                            <h3 className="font-bold text-slate-900 dark:text-white text-base truncate">{group.title}</h3>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs text-slate-400 font-medium">{group.category_type}</span>
                                                <span className="text-xs text-slate-300 dark:text-slate-600">|</span>
                                                <span className="text-xs text-slate-400">{groupPaid}/{groupTotal} \u00f6dendi</span>
                                                {group.total_amount > 0 && (
                                                    <>
                                                        <span className="text-xs text-slate-300 dark:text-slate-600">|</span>
                                                        <span className="text-xs font-bold text-slate-600 dark:text-slate-300">{fmtCurrency(group.total_amount)}</span>
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 flex-shrink-0">
                                        <button
                                            onClick={() => { resetItemForm(); setShowItemForm(group.id); }}
                                            className="p-2 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-all"
                                            title="Kalem Ekle"
                                        >
                                            <span className="material-icons-round text-lg">add_circle_outline</span>
                                        </button>
                                        <button
                                            onClick={() => openEditGroup(group)}
                                            className="p-2 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all"
                                            title="D\u00fczenle"
                                        >
                                            <span className="material-icons-round text-lg">edit</span>
                                        </button>
                                        <button
                                            onClick={() => setDeleteTarget({ type: 'group', id: group.id, label: group.title })}
                                            className="p-2 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                                            title="Sil"
                                        >
                                            <span className="material-icons-round text-lg">delete_outline</span>
                                        </button>
                                    </div>
                                </div>

                                {/* Items */}
                                {(!group.items || group.items.length === 0) ? (
                                    <div className="p-8 text-center text-slate-400">
                                        <span className="material-icons-round text-3xl opacity-20 mb-2 block">inbox</span>
                                        <p className="text-sm">Bu grupta hen\u00fcz kalem yok.</p>
                                        <button
                                            onClick={() => { resetItemForm(); setShowItemForm(group.id); }}
                                            className="mt-3 text-indigo-600 hover:text-indigo-700 text-sm font-bold inline-flex items-center gap-1"
                                        >
                                            <span className="material-icons-round text-sm">add</span>
                                            Kalem Ekle
                                        </button>
                                    </div>
                                ) : (
                                    <div className="divide-y divide-slate-50 dark:divide-slate-800">
                                        {group.items.map(item => {
                                            const sb = STATUS_BADGE[item.status] || STATUS_BADGE.pending;
                                            return (
                                                <div key={item.id} className="p-4 hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors group/item">
                                                    <div className="flex items-center gap-4">
                                                        {/* Payment Toggle */}
                                                        <button
                                                            onClick={() => handlePaymentToggle(item)}
                                                            className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-all ${
                                                                item.status === 'paid'
                                                                    ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400'
                                                                    : 'bg-slate-100 dark:bg-slate-800 text-slate-300 dark:text-slate-600 hover:bg-emerald-50 hover:text-emerald-500'
                                                            }`}
                                                            title={item.status === 'paid' ? 'Bekliyora \u00e7evir' : '\u00d6dendi olarak i\u015faretle'}
                                                        >
                                                            <span className="material-icons-round text-lg">
                                                                {item.status === 'paid' ? 'check' : 'radio_button_unchecked'}
                                                            </span>
                                                        </button>

                                                        {/* Info */}
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2 flex-wrap">
                                                                <p className={`font-bold text-sm ${item.status === 'paid' ? 'text-slate-400 line-through' : 'text-slate-900 dark:text-white'}`}>
                                                                    {item.name}
                                                                </p>
                                                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${sb.color}`}>
                                                                    {sb.label}
                                                                </span>
                                                            </div>
                                                            <p className="text-xs text-slate-400 mt-0.5">
                                                                Her ay\u0131n {item.day}. g\u00fcn\u00fc
                                                                {item.month_payment?.payment_date && ` \\u2014 Son \u00f6deme: ${new Date(item.month_payment.payment_date).toLocaleDateString('tr-TR')}`}
                                                            </p>
                                                        </div>

                                                        {/* Amount */}
                                                        <p className={`font-bold text-sm flex-shrink-0 ${item.status === 'paid' ? 'text-emerald-600' : 'text-slate-900 dark:text-white'}`}>
                                                            {fmtCurrency(item.amount)}
                                                        </p>

                                                        {/* Actions */}
                                                        <div className="flex items-center gap-0.5 opacity-0 group-hover/item:opacity-100 transition-opacity flex-shrink-0">
                                                            <button
                                                                onClick={() => openEditItem(item, group.id)}
                                                                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
                                                                title="D\u00fczenle"
                                                            >
                                                                <span className="material-icons-round text-base">edit</span>
                                                            </button>
                                                            <button
                                                                onClick={() => setDeleteTarget({ type: 'item', id: item.id, label: item.name })}
                                                                className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                                                                title="Sil"
                                                            >
                                                                <span className="material-icons-round text-base">delete_outline</span>
                                                            </button>
                                                        </div>
                                                    </div>

                                                    {/* Payment History (compact) */}
                                                    {item.history && item.history.length > 0 && (
                                                        <div className="ml-12 mt-2">
                                                            <div className="flex items-center gap-1 flex-wrap">
                                                                {item.history.slice(0, 5).map((h, idx) => (
                                                                    <span
                                                                        key={idx}
                                                                        className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${
                                                                            h.status === 'paid'
                                                                                ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400'
                                                                                : 'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500'
                                                                        }`}
                                                                        title={`${new Date(h.date).toLocaleDateString('tr-TR')} \\u2014 ${fmtCurrency(h.amount)}`}
                                                                    >
                                                                        {new Date(h.date).toLocaleDateString('tr-TR', { month: 'short' })}
                                                                    </span>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </DashboardLayout>
    );
};

export default Expenses;
"""

target = r"c:\Users\ahmet\OneDrive\Desktop\cloud-based-finance-app\finance-app-frontend\src\pages\Expenses.js"
with open(target, 'w', encoding='utf-8') as f:
    f.write(content)
print("OK - wrote", len(content), "chars")
