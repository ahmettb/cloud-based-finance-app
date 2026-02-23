import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

const Sidebar = ({ isOpen, onClose }) => {
    const { user, logout } = useAuth();

    const activeClass = "flex items-center gap-3 px-4 py-3 bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white rounded-xl font-bold transition-all shadow-sm ring-1 ring-slate-200 dark:ring-slate-700";
    const inactiveClass = "flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-300 rounded-xl transition-all font-medium";

    return (
        <aside className={`
            fixed top-0 left-0 h-full w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-50 
            transition-transform duration-300 ease-in-out
            md:translate-x-0 md:static md:flex md:flex-col md:justify-between
            ${isOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'}
            flex flex-col justify-between
        `}>
            <div className="p-6">
                <div className="flex items-center gap-3 text-primary mb-10">
                    <span className="material-icons-round text-3xl">query_stats</span>
                    <span className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">ParamNerede</span>
                </div>

                <nav className="space-y-2">
                    <NavLink to="/" onClick={onClose} className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">dashboard</span>
                        Dashboard
                    </NavLink>

                    <NavLink to="/incomes" onClick={onClose} className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">savings</span>
                        Gelirlerim
                    </NavLink>

                    <NavLink to="/receipts" onClick={onClose} className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">description</span>
                        Dokümanlar
                    </NavLink>

                    <NavLink to="/budget" onClick={onClose} className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">fact_check</span>
                        Bütçe Takibi
                    </NavLink>

                    <NavLink to="/expenses" onClick={onClose} className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">account_balance</span>
                        Gider Yönetimi
                    </NavLink>

                    <NavLink to="/reports" onClick={onClose} className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">pie_chart</span>
                        Raporlar
                    </NavLink>

                    <NavLink to="/insights" onClick={onClose} className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">psychology</span>
                        AI İçgörüler
                    </NavLink>

                    <NavLink to="/chat" onClick={onClose} className={({ isActive }) => isActive ? activeClass : inactiveClass}>
                        <span className="material-icons-round">chat</span>
                        AI Asistan
                    </NavLink>

                    <button onClick={() => { logout(); onClose && onClose(); }} className="w-full flex items-center gap-3 px-4 py-3 text-slate-500 hover:bg-red-50 hover:text-red-500 rounded-xl transition-all mt-8">
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
