import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

const Sidebar = () => {
    const { user, logout } = useAuth();

    const activeClass = "flex items-center gap-3 px-4 py-3 bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white rounded-xl font-bold transition-all shadow-sm ring-1 ring-slate-200 dark:ring-slate-700";
    const inactiveClass = "flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-300 rounded-xl transition-all font-medium";

    return (
        <aside className="fixed left-0 top-0 h-full w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-50 hidden md:flex flex-col justify-between">
            <div className="p-6">
                <div className="flex items-center gap-3 text-primary mb-10">
                    <span className="material-icons-round text-3xl">query_stats</span>
                    <span className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">FinAI</span>
                </div>

                <nav className="space-y-2">
                    <NavLink to="/" className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">dashboard</span>
                        Dashboard
                    </NavLink>

                    <NavLink to="/incomes" className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">savings</span>
                        Gelirlerim
                    </NavLink>

                    <NavLink to="/receipts" className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">description</span>
                        Dokümanlar
                    </NavLink>

                    <NavLink to="/planning" className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">fact_check</span>
                        Planlama
                    </NavLink>

                    <NavLink to="/reports" className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">pie_chart</span>
                        Raporlar
                    </NavLink>

                    <button onClick={logout} className="w-full flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-red-50 hover:text-red-500 rounded-xl transition-all mt-8">
                        <span className="material-icons-round">logout</span>
                        Çıkış Yap
                    </button>
                </nav>
            </div>

            <div className="p-6 border-t border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold overflow-hidden">
                        {user?.full_name?.charAt(0) || 'U'}
                    </div>
                    <div className="overflow-hidden">
                        <p className="text-sm font-bold truncate text-slate-900 dark:text-white">{user?.full_name || 'Kullanıcı'}</p>
                        <p className="text-xs text-slate-400 truncate">{user?.email}</p>
                    </div>
                </div>
            </div>
        </aside>
    );
};

export default Sidebar;
