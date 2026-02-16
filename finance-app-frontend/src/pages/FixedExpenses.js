import React, { useState, useMemo } from 'react';
import DashboardLayout from '../components/layout/DashboardLayout';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

const currencyFormatter = new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    maximumFractionDigits: 0
});

const dateFormatter = new Intl.DateTimeFormat('tr-TR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric'
});

// Mock Initial Data: Groups with detailed history
const MOCK_GROUPS = [
    {
        id: 101,
        title: 'Ev Giderleri',
        category_type: 'Kira',
        total_amount: 15700,
        items: [
            {
                id: 1,
                name: 'Kira',
                amount: 15000,
                day: 1,
                status: 'paid',
                history: [
                    { date: '2026-02-01', amount: 15000, status: 'paid' },
                    { date: '2026-01-01', amount: 14000, status: 'paid' },
                    { date: '2025-12-01', amount: 14000, status: 'paid' }
                ]
            },
            {
                id: 2,
                name: 'Aidat',
                amount: 700,
                day: 5,
                status: 'pending',
                history: [
                    { date: '2026-01-05', amount: 700, status: 'paid' },
                    { date: '2025-12-05', amount: 650, status: 'paid' }
                ]
            },
        ]
    },
    {
        id: 102,
        title: 'Faturalar',
        category_type: 'Fatura',
        total_amount: 1730,
        items: [
            { id: 3, name: 'Elektrik', amount: 450, day: 15, status: 'pending', history: [] },
            { id: 4, name: 'Su', amount: 250, day: 15, status: 'pending', history: [] },
            { id: 5, name: 'Doğalgaz', amount: 350, day: 20, status: 'pending', history: [] },
            { id: 6, name: 'İnternet', amount: 680, day: 10, status: 'overdue', history: [] },
        ]
    },
    {
        id: 103,
        title: 'Dijital Üyelikler',
        category_type: 'Abonelik',
        total_amount: 290,
        items: [
            {
                id: 7,
                name: 'Netflix',
                amount: 230,
                day: 22,
                status: 'pending',
                history: [
                    { date: '2026-01-22', amount: 230, status: 'paid' },
                    { date: '2025-12-22', amount: 199, status: 'paid' },
                    { date: '2025-11-22', amount: 199, status: 'paid' },
                ]
            },
            { id: 8, name: 'Spotify', amount: 60, day: 22, status: 'pending', history: [] },
        ]
    }
];

const GROUP_CATEGORIES = ['Kira', 'Fatura', 'Abonelik', 'Kredi', 'Eğitim', 'Diğer'];

const FixedExpenses = () => {
    const toast = useToast();
    const [groups, setGroups] = useState(MOCK_GROUPS);

    // Modal States
    const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
    const [isItemModalOpen, setIsItemModalOpen] = useState(false);
    const [isManualHistoryModalOpen, setIsManualHistoryModalOpen] = useState(false); // New modal for manual history

    const [selectedGroupId, setSelectedGroupId] = useState(null);
    const [selectedItemId, setSelectedItemId] = useState(null); // For manual history add

    const [expandedGroupIds, setExpandedGroupIds] = useState([101, 102, 103]);
    const [expandedItemMeta, setExpandedItemMeta] = useState(null); // { groupId, itemId }

    // Form States
    const [newGroup, setNewGroup] = useState({ title: '', category: 'Fatura' });
    const [newItem, setNewItem] = useState({ name: '', amount: '', day: 1 });
    const [manualHistory, setManualHistory] = useState({ date: '', amount: '' }); // For retro entry

    // Computed Stats
    const stats = useMemo(() => {
        let total = 0;
        let paid = 0;
        let count = 0;
        let pending_count = 0;

        groups.forEach(g => {
            g.items.forEach(i => {
                total += i.amount;
                count++;
                if (i.status === 'paid') paid += i.amount;
                else pending_count++;
            });
        });

        return { total, paid, remaining: total - paid, count, pending_count };
    }, [groups]);

    const handleCreateGroup = (e) => {
        e.preventDefault();
        const newGroupObj = {
            id: Date.now(),
            title: newGroup.title,
            category_type: newGroup.category,
            total_amount: 0,
            items: []
        };
        setGroups([...groups, newGroupObj]);
        setExpandedGroupIds([...expandedGroupIds, newGroupObj.id]);
        setNewGroup({ title: '', category: 'Fatura' });
        setIsGroupModalOpen(false);
        toast.show.success("Yeni gider grubu oluşturuldu");
    };

    const handleAddItem = (e) => {
        e.preventDefault();
        if (!selectedGroupId) return;

        const updatedGroups = groups.map(g => {
            if (g.id === selectedGroupId) {
                const item = {
                    id: Date.now(),
                    ...newItem,
                    amount: parseFloat(newItem.amount),
                    status: 'pending',
                    history: []
                };
                return {
                    ...g,
                    items: [...g.items, item],
                    total_amount: g.total_amount + item.amount
                };
            }
            return g;
        });

        setGroups(updatedGroups);
        setNewItem({ name: '', amount: '', day: 1 });
        setIsItemModalOpen(false);
        toast.show.success("Gider eklendi");
    };

    const handleAddManualHistory = (e) => {
        e.preventDefault();
        if (!selectedGroupId || !selectedItemId) return;

        const updatedGroups = groups.map(g => {
            if (g.id === selectedGroupId) {
                const updatedItems = g.items.map(i => {
                    if (i.id === selectedItemId) {
                        const newHistory = [...i.history];
                        newHistory.unshift({
                            date: manualHistory.date,
                            amount: parseFloat(manualHistory.amount),
                            status: 'paid'
                        });
                        // Sort history by date desc
                        newHistory.sort((a, b) => new Date(b.date) - new Date(a.date));
                        return { ...i, history: newHistory };
                    }
                    return i;
                });
                return { ...g, items: updatedItems };
            }
            return g;
        });
        setGroups(updatedGroups);
        setManualHistory({ date: '', amount: '' });
        setIsManualHistoryModalOpen(false);
        toast.show.success("Geçmiş ödeme kaydı eklendi");
    };

    const toggleGroup = (id) => {
        if (expandedGroupIds.includes(id)) {
            setExpandedGroupIds(expandedGroupIds.filter(gid => gid !== id));
        } else {
            setExpandedGroupIds([...expandedGroupIds, id]);
        }
    };

    const toggleItemHistory = (groupId, itemId) => {
        if (expandedItemMeta && expandedItemMeta.itemId === itemId) {
            setExpandedItemMeta(null);
        } else {
            setExpandedItemMeta({ groupId, itemId });
        }
    };

    const handleStatusToggle = (groupId, itemId) => {
        const updatedGroups = groups.map(g => {
            if (g.id === groupId) {
                const updatedItems = g.items.map(i => {
                    if (i.id === itemId) {
                        const newStatus = i.status === 'paid' ? 'pending' : 'paid';
                        // Mock adding to history when paid
                        let newHistory = [...i.history];
                        if (newStatus === 'paid') {
                            newHistory.unshift({
                                date: new Date().toISOString().split('T')[0],
                                amount: i.amount,
                                status: 'paid'
                            });
                        }
                        return { ...i, status: newStatus, history: newHistory };
                    }
                    return i;
                });
                return { ...g, items: updatedItems };
            }
            return g;
        });
        setGroups(updatedGroups);
        toast.show.success("Ödeme durumu güncellendi");
    };

    const openAddItemModal = (groupId) => {
        setSelectedGroupId(groupId);
        setIsItemModalOpen(true);
    };

    const openManualHistoryModal = (groupId, itemId, currentAmount) => {
        setSelectedGroupId(groupId);
        setSelectedItemId(itemId);
        setManualHistory({ date: new Date().toISOString().split('T')[0], amount: currentAmount });
        setIsManualHistoryModalOpen(true);
    };

    const getDaysRemaining = (day) => {
        const today = new Date().getDate();
        let diff = day - today;
        if (diff < 0) return `Geçti (${Math.abs(diff)} gün)`;
        if (diff === 0) return 'Bugün';
        if (diff === 1) return 'Yarın';
        return `${diff} gün kaldı`;
    };

    const getCategoryIcon = (cat) => {
        switch (cat) {
            case 'Kira': return 'home';
            case 'Fatura': return 'receipt_long';
            case 'Abonelik': return 'subscriptions';
            case 'Kredi': return 'credit_card';
            case 'Eğitim': return 'school';
            default: return 'category';
        }
    };

    return (
        <DashboardLayout>
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        Sabit Giderler
                        <span className="bg-indigo-100 text-indigo-700 text-xs px-2 py-1 rounded-full">{stats.count} Kalem</span>
                    </h1>
                    <p className="text-slate-500 text-sm mt-1">Ödemelerinizi gruplayarak daha düzenli takip edin.</p>
                </div>
                <button
                    onClick={() => setIsGroupModalOpen(true)}
                    className="bg-slate-900 dark:bg-slate-700 text-white px-4 py-2 rounded-xl flex items-center gap-2 font-bold shadow-lg transition-all text-sm"
                >
                    <span className="material-icons-round text-base">create_new_folder</span>
                    Yeni Grup
                </button>
            </div>

            {/* Top Stats */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                <div className="bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-2xl p-5 text-white shadow-lg shadow-indigo-200 dark:shadow-none">
                    <p className="opacity-80 text-xs font-bold uppercase mb-1">Toplam Aylık Yük</p>
                    <h2 className="text-3xl font-bold tracking-tight">{currencyFormatter.format(stats.total)}</h2>
                    <div className="mt-3 bg-black/20 rounded-lg p-2 flex justify-between items-center text-xs font-medium">
                        <span>Ödenen: {currencyFormatter.format(stats.paid)}</span>
                        <span>% {Math.round((stats.paid / stats.total) * 100)}</span>
                    </div>
                </div>

                <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-center">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="w-10 h-10 rounded-full bg-amber-50 text-amber-500 flex items-center justify-center">
                            <span className="material-icons-round">pending</span>
                        </div>
                        <div>
                            <p className="text-slate-500 text-xs font-bold uppercase">Bekleyen Ödemeler</p>
                            <h3 className="text-xl font-bold text-slate-800 dark:text-white">{stats.pending_count} Adet</h3>
                        </div>
                    </div>
                    <p className="text-xs text-amber-600 font-bold mt-1">Toplam: {currencyFormatter.format(stats.remaining)}</p>
                </div>

                <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-center">
                    <p className="text-slate-500 text-xs font-bold uppercase mb-3">Kategori Dağılımı</p>
                    <div className="flex gap-2 h-16 items-end">
                        {groups.slice(0, 4).map(g => {
                            const h = stats.total > 0 ? (g.total_amount / stats.total) * 100 : 0;
                            return (
                                <div key={g.id} className="flex-1 flex flex-col items-center gap-1 group/bar">
                                    <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-t-lg relative transition-all hover:bg-indigo-100" style={{ height: `${Math.max(h, 20)}%` }}>
                                        <div className="absolute -top-6 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] px-1.5 py-0.5 rounded opacity-0 group-hover/bar:opacity-100 transition-opacity whitespace-nowrap z-10">
                                            {currencyFormatter.format(g.total_amount)}
                                        </div>
                                    </div>
                                    <span className="text-[9px] font-bold text-slate-400 truncate w-full text-center">{g.title.split(' ')[0]}</span>
                                </div>
                            )
                        })}
                    </div>
                </div>
            </div>

            {/* Groups Grid */}
            <div className="space-y-6">
                {groups.map((group) => (
                    <div key={group.id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden transition-all">
                        {/* Group Header */}
                        <div
                            className="p-5 flex items-center justify-between cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
                            onClick={() => toggleGroup(group.id)}
                        >
                            <div className="flex items-center gap-4">
                                <button className={`w-8 h-8 rounded-full flex items-center justify-center transition-transform ${expandedGroupIds.includes(group.id) ? 'rotate-90 bg-slate-100 text-slate-600' : 'text-slate-400'}`}>
                                    <span className="material-icons-round">chevron_right</span>
                                </button>
                                <div>
                                    <h3 className="font-bold text-lg text-slate-800 dark:text-white flex items-center gap-2">
                                        <span className="material-icons-round text-slate-400 text-lg">{getCategoryIcon(group.category_type)}</span>
                                        {group.title}
                                        <span className="text-xs bg-slate-100 dark:bg-slate-800 text-slate-500 px-2 py-0.5 rounded-full font-medium">{group.items.length} kalem</span>
                                    </h3>
                                    <p className="text-xs text-slate-400 mt-0.5 ml-7">Toplam Yük: {currencyFormatter.format(group.total_amount)}</p>
                                </div>
                            </div>

                            <div className="flex items-center gap-3">
                                <div className="hidden sm:flex items-center gap-1.5 mr-4">
                                    <div className="w-24 h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-emerald-500 rounded-full transition-all duration-500"
                                            style={{ width: `${(group.items.filter(i => i.status === 'paid').reduce((a, b) => a + b.amount, 0) / group.total_amount) * 100}%` }}
                                        ></div>
                                    </div>
                                </div>
                                <button
                                    onClick={(e) => { e.stopPropagation(); openAddItemModal(group.id); }}
                                    className="w-8 h-8 rounded-lg border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:border-indigo-200 hover:bg-indigo-50 transition-all"
                                    title="Bu gruba gider ekle"
                                >
                                    <span className="material-icons-round text-lg">add</span>
                                </button>
                            </div>
                        </div>

                        {/* Group Items (Collapsible) */}
                        {expandedGroupIds.includes(group.id) && (
                            <div className="border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20">
                                {group.items.length > 0 ? (
                                    <div className="divide-y divide-slate-100 dark:divide-slate-800">
                                        {group.items.map((item) => (
                                            <div key={item.id} className="flex flex-col">
                                                {/* Main Row */}
                                                <div
                                                    className={`p-4 pl-16 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 hover:bg-white dark:hover:bg-slate-800 transition-colors cursor-pointer ${expandedItemMeta?.itemId === item.id ? 'bg-white dark:bg-slate-800 shadow-inner' : ''}`}
                                                    onClick={() => toggleItemHistory(group.id, item.id)}
                                                >
                                                    <div className="flex items-center gap-4">
                                                        <div className={`w-2 h-2 rounded-full ${item.status === 'paid' ? 'bg-emerald-400' : (item.status === 'overdue' ? 'bg-red-400' : 'bg-amber-400')}`}></div>
                                                        <div>
                                                            <div className="flex items-center gap-2">
                                                                <p className={`font-bold text-sm ${item.status === 'paid' ? 'text-slate-400 line-through' : 'text-slate-800 dark:text-slate-200'}`}>{item.name}</p>
                                                                {item.history && item.history.length > 0 && (
                                                                    <span className="text-[10px] items-center flex bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-300 px-1.5 rounded-md">
                                                                        <span className="material-icons-round text-[10px] mr-1">history</span>
                                                                        {item.history.length}
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <p className="text-[10px] text-slate-400">Her ayın {item.day}. günü • {getDaysRemaining(item.day)}</p>
                                                        </div>
                                                    </div>

                                                    <div className="flex items-center gap-4 w-full sm:w-auto justify-between sm:justify-end pl-6 sm:pl-0">
                                                        <span className={`font-bold text-sm ${item.status === 'paid' ? 'text-slate-400' : 'text-slate-900 dark:text-white'}`}>
                                                            {currencyFormatter.format(item.amount)}
                                                        </span>

                                                        <div className="flex items-center gap-2">
                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); openManualHistoryModal(group.id, item.id, item.amount); }}
                                                                className="w-8 h-8 rounded-lg border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-all"
                                                                title="Geçmiş Ödeme Ekle"
                                                            >
                                                                <span className="material-icons-round text-sm">post_add</span>
                                                            </button>

                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); handleStatusToggle(group.id, item.id); }}
                                                                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${item.status === 'paid'
                                                                        ? 'bg-emerald-50 text-emerald-600 border-emerald-200 hover:bg-red-50 hover:text-red-500 hover:border-red-200'
                                                                        : 'bg-white text-slate-500 border-slate-200 hover:bg-emerald-50 hover:text-emerald-600 hover:border-emerald-200 shadow-sm'
                                                                    }`}
                                                            >
                                                                {item.status === 'paid' ? 'Ödendi' : 'Öde'}
                                                            </button>
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* History Sub-Row */}
                                                {expandedItemMeta?.itemId === item.id && (
                                                    <div className="bg-slate-100 dark:bg-slate-900/50 p-4 pl-20 pr-8 text-xs animate-fade-in border-t border-slate-100 dark:border-slate-800">
                                                        <div className="flex justify-between items-center mb-2">
                                                            <p className="font-bold text-slate-500 uppercase text-[10px]">Ödeme Geçmişi</p>
                                                            <button
                                                                onClick={(e) => { e.stopPropagation(); openManualHistoryModal(group.id, item.id, item.amount); }}
                                                                className="text-indigo-600 font-bold hover:underline"
                                                            >
                                                                + Geçmiş Ekle
                                                            </button>
                                                        </div>
                                                        {item.history && item.history.length > 0 ? (
                                                            <div className="space-y-2">
                                                                {item.history.map((hist, idx) => (
                                                                    <div key={idx} className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-2 last:border-0 last:pb-0">
                                                                        <span className="text-slate-600 dark:text-slate-400">{dateFormatter.format(new Date(hist.date))}</span>
                                                                        <div className="flex items-center gap-2">
                                                                            <span className="font-bold text-slate-700 dark:text-slate-300">{currencyFormatter.format(hist.amount)}</span>
                                                                            <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded flex items-center gap-1">
                                                                                <span className="material-icons-round text-[10px]">check</span> Ödendi
                                                                            </span>
                                                                        </div>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        ) : (
                                                            <p className="text-slate-400 italic">Henüz geçmiş ödeme kaydı bulunmuyor.</p>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="p-6 text-center text-slate-400 text-xs italic">
                                        Bu grupta henüz hiç gider kalemi yok.
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* Create Group Modal */}
            {isGroupModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-sm p-6 animate-scale-in">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Yeni Gider Grubu</h2>
                        <form onSubmit={handleCreateGroup} className="space-y-4">
                            <div>
                                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Başlık</label>
                                <input
                                    autoFocus
                                    type="text"
                                    placeholder="Örn: Ev Giderleri"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-indigo-500"
                                    value={newGroup.title}
                                    onChange={e => setNewGroup({ ...newGroup, title: e.target.value })}
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Kategori Tipi</label>
                                <div className="grid grid-cols-3 gap-2">
                                    {GROUP_CATEGORIES.map(cat => (
                                        <button
                                            key={cat}
                                            type="button"
                                            onClick={() => setNewGroup({ ...newGroup, category: cat })}
                                            className={`py-2 rounded-xl text-xs font-bold transition-all ${newGroup.category === cat
                                                ? 'bg-slate-900 text-white shadow-md'
                                                : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                                                }`}
                                        >
                                            {cat}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="flex gap-2 pt-2">
                                <button type="button" onClick={() => setIsGroupModalOpen(false)} className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold py-3 rounded-xl text-sm transition-colors">İptal</button>
                                <button type="submit" className="flex-1 bg-slate-900 hover:bg-slate-800 text-white font-bold py-3 rounded-xl text-sm transition-colors shadow-lg shadow-slate-200">Oluştur</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Add Item Modal */}
            {isItemModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-sm p-6 animate-scale-in">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Yeni Gider Ekle</h2>
                        <p className="text-xs text-slate-500 mb-4">Seçili gruba yeni bir kalem ekliyorsunuz.</p>

                        <form onSubmit={handleAddItem} className="space-y-3">
                            <div>
                                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Gider Adı</label>
                                <input
                                    type="text"
                                    placeholder="Örn: Mutfak Masrafı"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2.5 text-sm font-bold outline-none focus:ring-2 focus:ring-indigo-500"
                                    value={newItem.name}
                                    onChange={e => setNewItem({ ...newItem, name: e.target.value })}
                                    required
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Tutar (TL)</label>
                                    <input
                                        type="number"
                                        placeholder="0.00"
                                        className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2.5 text-sm font-bold outline-none focus:ring-2 focus:ring-indigo-500"
                                        value={newItem.amount}
                                        onChange={e => setNewItem({ ...newItem, amount: e.target.value })}
                                        required
                                    />
                                </div>
                                <div>
                                    <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Ödeme Günü</label>
                                    <input
                                        type="number"
                                        min="1" max="31"
                                        placeholder="Gün"
                                        className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2.5 text-sm font-bold outline-none focus:ring-2 focus:ring-indigo-500"
                                        value={newItem.day}
                                        onChange={e => setNewItem({ ...newItem, day: parseInt(e.target.value) })}
                                        required
                                    />
                                </div>
                            </div>

                            <div className="flex gap-2 pt-2">
                                <button type="button" onClick={() => setIsItemModalOpen(false)} className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold py-3 rounded-xl text-sm transition-colors">İptal</button>
                                <button type="submit" className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-xl text-sm transition-colors shadow-lg shadow-indigo-200">Kaydet</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Manual History Modal */}
            {isManualHistoryModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-sm p-6 animate-scale-in">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-1">Geçmiş Ödeme Ekle</h2>
                        <p className="text-xs text-slate-500 mb-4">Unuttuğunuz veya geçmişte yaptığınız bir ödemeyi ekleyin.</p>

                        <form onSubmit={handleAddManualHistory} className="space-y-3">
                            <div>
                                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Tarih</label>
                                <input
                                    type="date"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2.5 text-sm font-bold outline-none focus:ring-2 focus:ring-indigo-500"
                                    value={manualHistory.date}
                                    onChange={e => setManualHistory({ ...manualHistory, date: e.target.value })}
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Tutar (TL)</label>
                                <input
                                    type="number"
                                    className="w-full bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2.5 text-sm font-bold outline-none focus:ring-2 focus:ring-indigo-500"
                                    value={manualHistory.amount}
                                    onChange={e => setManualHistory({ ...manualHistory, amount: e.target.value })}
                                    required
                                />
                            </div>

                            <div className="flex gap-2 pt-2">
                                <button type="button" onClick={() => setIsManualHistoryModalOpen(false)} className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold py-3 rounded-xl text-sm transition-colors">İptal</button>
                                <button type="submit" className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-xl text-sm transition-colors shadow-lg shadow-indigo-200">Ekle</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

        </DashboardLayout>
    );
};

export default FixedExpenses;
