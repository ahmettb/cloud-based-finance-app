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

// Mock Data: Fixed Expenses
const MOCK_FIXED_GROUPS = [
    {
        id: 101,
        title: 'Ev Giderleri',
        category_type: 'Kira',
        items: [
            { id: 1, name: 'Kira', amount: 15000, day: 1, status: 'paid', history: [] },
            { id: 2, name: 'Aidat', amount: 700, day: 5, status: 'pending', history: [] },
        ]
    },
    {
        id: 102,
        title: 'Faturalar',
        category_type: 'Fatura',
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
        items: [
            { id: 7, name: 'Netflix', amount: 230, day: 22, status: 'pending', history: [] },
            { id: 8, name: 'Spotify', amount: 60, day: 22, status: 'pending', history: [] },
        ]
    }
];

// Mock Data: Variable Expenses (From Receipts/Manual)
const MOCK_VARIABLE_EXPENSES = [
    { id: 201, date: '2026-02-15', category: 'Market', merchant: 'Migros', amount: 1250.50, description: 'Haftalık alışveriş' },
    { id: 202, date: '2026-02-14', category: 'Restoran', merchant: 'Happy Moons', amount: 850.00, description: 'Akşam yemeği' },
    { id: 203, date: '2026-02-12', category: 'Ulaşım', merchant: 'Shell', amount: 1500.00, description: 'Benzin' },
    { id: 204, date: '2026-02-10', category: 'Kafe', merchant: 'Starbucks', amount: 145.00, description: 'Kahve' },
    { id: 205, date: '2026-02-08', category: 'Market', merchant: 'Bim', amount: 320.00, description: 'Ara eksikler' },
];

const GROUP_CATEGORIES = ['Kira', 'Fatura', 'Abonelik', 'Kredi', 'Eğitim', 'Diğer'];
const VARIABLE_CATEGORIES = ['Market', 'Restoran', 'Kafe', 'Ulaşım', 'Giyim', 'Sağlık', 'Eğlence', 'Teknoloji', 'Diğer'];

const Expenses = () => {
    const toast = useToast();
    const [activeTab, setActiveTab] = useState('fixed'); // 'fixed' | 'variable'
    const [fixedGroups, setFixedGroups] = useState(MOCK_FIXED_GROUPS);
    const [variableExpenses, setVariableExpenses] = useState(MOCK_VARIABLE_EXPENSES);

    // Filter States for Variable Expenses
    const [variableFilterDate, setVariableFilterDate] = useState('2026-02');
    const [variableFilterCategory, setVariableFilterCategory] = useState('all');

    // Stats Calculation
    const fixedStats = useMemo(() => {
        let total = 0, paid = 0, count = 0, pending_count = 0;
        fixedGroups.forEach(g => {
            g.items.forEach(i => {
                total += i.amount;
                count++;
                if (i.status === 'paid') paid += i.amount;
                else pending_count++;
            });
        });
        return { total, paid, remaining: total - paid, count, pending_count };
    }, [fixedGroups]);

    const variableStats = useMemo(() => {
        const filtered = variableExpenses.filter(e => {
            const dateMatch = e.date.startsWith(variableFilterDate);
            const catMatch = variableFilterCategory === 'all' || e.category === variableFilterCategory;
            return dateMatch && catMatch;
        });

        const total = filtered.reduce((acc, curr) => acc + curr.amount, 0);

        // Group by category for chart/distribution
        const distribution = filtered.reduce((acc, curr) => {
            acc[curr.category] = (acc[curr.category] || 0) + curr.amount;
            return acc;
        }, {});

        return { total, count: filtered.length, filtered, distribution };
    }, [variableExpenses, variableFilterDate, variableFilterCategory]);

    // --- Fixed Expenses Logic ---
    const [expandedGroupIds, setExpandedGroupIds] = useState([101, 102]);
    const [expandedItemMeta, setExpandedItemMeta] = useState(null);
    const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
    const [isItemModalOpen, setIsItemModalOpen] = useState(false);
    const [isManualHistoryModalOpen, setIsManualHistoryModalOpen] = useState(false);
    const [selectedGroupId, setSelectedGroupId] = useState(null);
    const [selectedItemId, setSelectedItemId] = useState(null);

    const [newGroup, setNewGroup] = useState({ title: '', category: 'Fatura' });
    const [newItem, setNewItem] = useState({ name: '', amount: '', day: 1 });
    const [manualHistory, setManualHistory] = useState({ date: '', amount: '' });

    const toggleGroup = (id) => {
        if (expandedGroupIds.includes(id)) setExpandedGroupIds(expandedGroupIds.filter(gid => gid !== id));
        else setExpandedGroupIds([...expandedGroupIds, id]);
    };

    const handleCreateGroup = (e) => {
        e.preventDefault();
        const newGroupObj = { id: Date.now(), title: newGroup.title, category_type: newGroup.category, items: [] };
        setFixedGroups([...fixedGroups, newGroupObj]);
        setExpandedGroupIds([...expandedGroupIds, newGroupObj.id]);
        setIsGroupModalOpen(false);
        toast.show.success("Grup oluşturuldu");
    };

    const handleAddItem = (e) => {
        e.preventDefault();
        const updated = fixedGroups.map(g => {
            if (g.id === selectedGroupId) {
                return { ...g, items: [...g.items, { id: Date.now(), ...newItem, amount: parseFloat(newItem.amount), status: 'pending', history: [] }] };
            }
            return g;
        });
        setFixedGroups(updated);
        setIsItemModalOpen(false);
        toast.show.success("Gider eklendi");
    };

    const handleStatusToggle = (groupId, itemId) => {
        const updated = fixedGroups.map(g => {
            if (g.id === groupId) {
                return {
                    ...g, items: g.items.map(i => {
                        if (i.id === itemId) return { ...i, status: i.status === 'paid' ? 'pending' : 'paid' };
                        return i;
                    })
                };
            }
            return g;
        });
        setFixedGroups(updated);
    };

    // --- Variable Expenses Logic ---
    const [isVariableModalOpen, setIsVariableModalOpen] = useState(false);
    const [newVariable, setNewVariable] = useState({ date: new Date().toISOString().split('T')[0], category: 'Market', merchant: '', amount: '', description: '' });

    const handleAddVariable = (e) => {
        e.preventDefault();
        const expense = {
            id: Date.now(),
            ...newVariable,
            amount: parseFloat(newVariable.amount)
        };
        setVariableExpenses([expense, ...variableExpenses]);
        setIsVariableModalOpen(false);
        setNewVariable({ date: new Date().toISOString().split('T')[0], category: 'Market', merchant: '', amount: '', description: '' });
        toast.show.success("Harcama eklendi");
    };

    // Helper Functions
    const getCategoryIcon = (cat) => {
        const map = {
            'Kira': 'home', 'Fatura': 'receipt_long', 'Abonelik': 'subscriptions', 'Kredi': 'credit_card',
            'Market': 'shopping_cart', 'Restoran': 'restaurant', 'Kafe': 'coffee', 'Ulaşım': 'commute',
            'Giyim': 'checkroom', 'Sağlık': 'medical_services', 'Eğlence': 'theater_comedy', 'Teknoloji': 'laptop', 'Diğer': 'category'
        };
        return map[cat] || 'category';
    };

    return (
        <DashboardLayout>
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">Gider Yönetimi</h1>
                <p className="text-slate-500 text-sm mt-1">Sabit ödemelerinizi ve aylık değişken harcamalarınızı tek yerden yönetin.</p>
            </div>

            {/* Main Tabs */}
            <div className="flex gap-4 border-b border-slate-200 dark:border-slate-800 mb-6">
                <button
                    onClick={() => setActiveTab('fixed')}
                    className={`pb-3 px-4 text-sm font-bold transition-all relative flex items-center gap-2 ${activeTab === 'fixed' ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}
                >
                    <span className="material-icons-round text-lg">event_repeat</span>
                    Sabit Giderler
                    <span className="bg-slate-100 text-slate-600 text-[10px] px-1.5 py-0.5 rounded-full">{fixedStats.count}</span>
                </button>
                <button
                    onClick={() => setActiveTab('variable')}
                    className={`pb-3 px-4 text-sm font-bold transition-all relative flex items-center gap-2 ${activeTab === 'variable' ? 'text-indigo-600 border-b-2 border-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}
                >
                    <span className="material-icons-round text-lg">receipt</span>
                    Düzensiz Giderler
                    <span className="bg-slate-100 text-slate-600 text-[10px] px-1.5 py-0.5 rounded-full">{variableStats.count}</span>
                </button>
            </div>

            {/* --- FIXED EXPENSES TAB --- */}
            {activeTab === 'fixed' && (
                <div className="animate-fade-in">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                        {/* Stats Cards */}
                        <div className="bg-gradient-to-br from-indigo-500 to-indigo-600 rounded-2xl p-5 text-white shadow-lg shadow-indigo-200 dark:shadow-none">
                            <p className="opacity-80 text-xs font-bold uppercase mb-1">Aylık Sabit Yük</p>
                            <h2 className="text-3xl font-bold tracking-tight">{currencyFormatter.format(fixedStats.total)}</h2>
                            <div className="mt-3 bg-black/20 rounded-lg p-2 flex justify-between items-center text-xs font-medium">
                                <span>Ödenen: {currencyFormatter.format(fixedStats.paid)}</span>
                                <span>% {fixedStats.total > 0 ? Math.round((fixedStats.paid / fixedStats.total) * 100) : 0}</span>
                            </div>
                        </div>
                        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-center">
                            <div className="flex items-center gap-3 mb-2">
                                <div className="w-10 h-10 rounded-full bg-amber-50 text-amber-500 flex items-center justify-center">
                                    <span className="material-icons-round">pending</span>
                                </div>
                                <div>
                                    <p className="text-slate-500 text-xs font-bold uppercase">Bekleyen</p>
                                    <h3 className="text-xl font-bold text-slate-800 dark:text-white">{fixedStats.pending_count} Adet</h3>
                                </div>
                            </div>
                            <p className="text-xs text-amber-600 font-bold mt-1">Kalan Tutar: {currencyFormatter.format(fixedStats.remaining)}</p>
                        </div>
                        <div className="bg-indigo-50 dark:bg-slate-800/50 rounded-2xl p-5 border border-indigo-100 dark:border-indigo-900/30 flex items-center justify-between cursor-pointer hover:bg-indigo-100 transition-colors" onClick={() => setIsGroupModalOpen(true)}>
                            <div>
                                <h3 className="text-indigo-900 dark:text-indigo-100 font-bold text-lg">Yeni Grup</h3>
                                <p className="text-indigo-500 dark:text-indigo-400 text-xs mt-1">Sabit gider grubu oluştur</p>
                            </div>
                            <span className="material-icons-round text-3xl text-indigo-500">add_circle</span>
                        </div>
                    </div>

                    <div className="space-y-6">
                        {fixedGroups.map((group) => (
                            <div key={group.id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden transition-all">
                                <div className="p-5 flex items-center justify-between cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors" onClick={() => toggleGroup(group.id)}>
                                    <div className="flex items-center gap-4">
                                        <button className={`w-8 h-8 rounded-full flex items-center justify-center transition-transform ${expandedGroupIds.includes(group.id) ? 'rotate-90 bg-slate-100 text-slate-600' : 'text-slate-400'}`}>
                                            <span className="material-icons-round">chevron_right</span>
                                        </button>
                                        <div>
                                            <h3 className="font-bold text-lg text-slate-800 dark:text-white flex items-center gap-2">
                                                <span className="material-icons-round text-slate-400 text-lg">{getCategoryIcon(group.category_type)}</span>
                                                {group.title}
                                            </h3>
                                            <p className="text-xs text-slate-400 mt-0.5 ml-7">Toplam: {currencyFormatter.format(group.items.reduce((acc, curr) => acc + curr.amount, 0))}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <button onClick={(e) => { e.stopPropagation(); setSelectedGroupId(group.id); setIsItemModalOpen(true); }} className="w-8 h-8 rounded-lg border border-slate-200 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 flex items-center justify-center transition-all"><span className="material-icons-round text-lg">add</span></button>
                                    </div>
                                </div>
                                {expandedGroupIds.includes(group.id) && (
                                    <div className="border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20 divide-y divide-slate-100 dark:divide-slate-800">
                                        {group.items.map((item) => (
                                            <div key={item.id} className="p-4 pl-16 flex flex-col sm:flex-row items-center justify-between gap-3 hover:bg-white dark:hover:bg-slate-800 transition-colors">
                                                <div className="flex items-center gap-4">
                                                    <div className={`w-2 h-2 rounded-full ${item.status === 'paid' ? 'bg-emerald-400' : 'bg-amber-400'}`}></div>
                                                    <div>
                                                        <p className={`font-bold text-sm ${item.status === 'paid' ? 'text-slate-400 line-through' : 'text-slate-800 dark:text-slate-200'}`}>{item.name}</p>
                                                        <p className="text-[10px] text-slate-400">Her ayın {item.day}. günü</p>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-4">
                                                    <span className={`font-bold text-sm ${item.status === 'paid' ? 'text-slate-400' : 'text-slate-900 dark:text-white'}`}>{currencyFormatter.format(item.amount)}</span>
                                                    <button onClick={() => handleStatusToggle(group.id, item.id)} className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all ${item.status === 'paid' ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-white text-slate-500 border-slate-200 hover:border-emerald-200 hover:text-emerald-600'}`}>{item.status === 'paid' ? 'Ödendi' : 'Öde'}</button>
                                                </div>
                                            </div>
                                        ))}
                                        {group.items.length === 0 && <p className="text-center text-xs text-slate-400 p-4 italic">Kalem yok.</p>}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* --- VARIABLE EXPENSES TAB --- */}
            {activeTab === 'variable' && (
                <div className="animate-fade-in">
                    {/* Filters & Actions */}
                    <div className="flex flex-col md:flex-row gap-4 mb-6 justify-between items-end md:items-center bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
                        <div className="flex gap-4 w-full md:w-auto">
                            <div>
                                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Dönem</label>
                                <input type="month" className="bg-slate-50 dark:bg-slate-800 border-none rounded-lg text-xs font-bold py-2 px-3 outline-none" value={variableFilterDate} onChange={(e) => setVariableFilterDate(e.target.value)} />
                            </div>
                            <div>
                                <label className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Kategori</label>
                                <select className="bg-slate-50 dark:bg-slate-800 border-none rounded-lg text-xs font-bold py-2 px-3 outline-none" value={variableFilterCategory} onChange={(e) => setVariableFilterCategory(e.target.value)}>
                                    <option value="all">Tümü</option>
                                    {VARIABLE_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </div>
                        </div>
                        <div className="flex items-center gap-4">
                            <div className="text-right">
                                <p className="text-[10px] text-slate-400 font-bold uppercase">Toplam Harcama</p>
                                <p className="text-xl font-bold text-slate-900 dark:text-white">{currencyFormatter.format(variableStats.total)}</p>
                            </div>
                            <button onClick={() => setIsVariableModalOpen(true)} className="bg-slate-900 text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2 hover:bg-slate-800 transition-all shadow-lg shadow-slate-200"><span className="material-icons-round">add</span> Ekle</button>
                        </div>
                    </div>

                    {/* AI Insight Placeholder */}
                    <div className="bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-slate-800 dark:to-slate-800/50 rounded-2xl p-4 mb-6 border border-purple-100 dark:border-slate-700 flex items-start gap-4">
                        <div className="w-10 h-10 rounded-full bg-white dark:bg-slate-700 flex items-center justify-center text-purple-600 shadow-sm shrink-0">
                            <span className="material-icons-round">auto_awesome</span>
                        </div>
                        <div>
                            <h4 className="font-bold text-purple-900 dark:text-white text-sm">Yapay Zeka Analizi</h4>
                            <p className="text-xs text-purple-700 dark:text-slate-300 mt-1 leading-relaxed">
                                {variableStats.total > 5000
                                    ? "Bu ay değişken harcamalarınız ortalamanın üzerinde seyrediyor. Özellikle 'Market' ve 'Akaryakıt' kalemlerinde artış gözlemledim. Nakit akışınızı dengelemek için harcamalarınızı gözden geçirebilirsiniz."
                                    : "Harcamalarınız şu an için bütçe limitleri dahilinde ve dengeli görünüyor. Tasarruf potansiyeli olan kategoriler: 'Kafe' ve 'Eğlence'."}
                            </p>
                        </div>
                    </div>

                    {/* Chart / List Split */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        {/* Left: Distribution */}
                        <div className="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200 dark:border-slate-800 shadow-sm h-fit">
                            <h3 className="font-bold text-slate-900 dark:text-white text-sm mb-4">Kategori Dağılımı</h3>
                            <div className="space-y-3">
                                {Object.entries(variableStats.distribution).sort(([, a], [, b]) => b - a).map(([cat, amount]) => (
                                    <div key={cat}>
                                        <div className="flex justify-between text-xs font-bold mb-1">
                                            <span className="flex items-center gap-1 text-slate-600 dark:text-slate-400">
                                                <span className="material-icons-round text-sm">{getCategoryIcon(cat)}</span> {cat}
                                            </span>
                                            <span>{currencyFormatter.format(amount)}</span>
                                        </div>
                                        <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                            <div className="bg-indigo-500 h-full rounded-full" style={{ width: `${(amount / variableStats.total) * 100}%` }}></div>
                                        </div>
                                    </div>
                                ))}
                                {Object.keys(variableStats.distribution).length === 0 && <p className="text-secondary text-center text-xs italic py-4">Veri yok.</p>}
                            </div>
                        </div>

                        {/* Right: List */}
                        <div className="lg:col-span-2 space-y-3">
                            {variableStats.filtered.length > 0 ? variableStats.filtered.map(expense => (
                                <div key={expense.id} className="bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-between hover:shadow-md transition-all group">
                                    <div className="flex items-center gap-4">
                                        <div className="w-10 h-10 rounded-full bg-slate-50 dark:bg-slate-800 flex items-center justify-center text-slate-500">
                                            <span className="material-icons-round">{getCategoryIcon(expense.category)}</span>
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-slate-900 dark:text-white text-sm">{expense.merchant}</h4>
                                            <div className="flex items-center gap-2 text-[10px] text-slate-400 mt-0.5">
                                                <span className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-slate-500">{expense.category}</span>
                                                <span>•</span>
                                                <span>{dateFormatter.format(new Date(expense.date))}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className="font-bold text-slate-900 dark:text-white">{currencyFormatter.format(expense.amount)}</p>
                                        {expense.description && <p className="text-[10px] text-slate-400">{expense.description}</p>}
                                    </div>
                                </div>
                            )) : (
                                <div className="text-center py-10 bg-slate-50 dark:bg-slate-800/50 rounded-2xl border border-dashed border-slate-200 dark:border-slate-800">
                                    <span className="material-icons-round text-4xl text-slate-300">receipt_long</span>
                                    <p className="text-slate-400 text-sm mt-2">Bu kritere uygun harcama bulunamadı.</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Modals are placed here (Group, Item, Variable Expense) - simplified for brevity, logic exists above */}
            {isVariableModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
                    <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-xl w-full max-w-sm p-6 animate-scale-in">
                        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Yeni Harcama Ekle</h2>
                        <form onSubmit={handleAddVariable} className="space-y-3">
                            <input type="date" className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold" value={newVariable.date} onChange={e => setNewVariable({ ...newVariable, date: e.target.value })} required />
                            <input type="text" placeholder="Firma / Yer (Örn: Migros)" className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold" value={newVariable.merchant} onChange={e => setNewVariable({ ...newVariable, merchant: e.target.value })} required />
                            <select className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold" value={newVariable.category} onChange={e => setNewVariable({ ...newVariable, category: e.target.value })}>
                                {VARIABLE_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                            <input type="number" placeholder="Tutar" className="w-full bg-slate-50 dark:bg-slate-800 border-none rounded-xl p-3 text-sm font-bold" value={newVariable.amount} onChange={e => setNewVariable({ ...newVariable, amount: e.target.value })} required />
                            <div className="flex gap-2 pt-2">
                                <button type="button" onClick={() => setIsVariableModalOpen(false)} className="flex-1 bg-slate-100 dark:bg-slate-800 text-slate-500 font-bold py-3 rounded-xl text-sm">İptal</button>
                                <button type="submit" className="flex-1 bg-indigo-600 text-white font-bold py-3 rounded-xl text-sm">Kaydet</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Reuse existing Group/Item modals here from previous implementations... */}
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
        </DashboardLayout>
    );
};

export default Expenses;
