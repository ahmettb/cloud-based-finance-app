import React, { useState } from 'react';
import Sidebar from './Sidebar';

const DashboardLayout = ({ children }) => {
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

    return (
        <div className="flex h-screen bg-transparent text-slate-900 dark:text-slate-100 font-display">
            {/* Mobile Menu Button */}
            <div className="md:hidden fixed top-4 left-4 z-40">
                <button
                    onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                    className="p-2 bg-white dark:bg-slate-800 rounded-lg shadow-md text-slate-600 dark:text-slate-300 hover:text-indigo-600 transition-colors"
                >
                    <span className="material-icons-round text-2xl">
                        {isMobileMenuOpen ? 'close' : 'menu'}
                    </span>
                </button>
            </div>

            {/* Sidebar */}
            <div className="print:hidden">
                <Sidebar isOpen={isMobileMenuOpen} onClose={() => setIsMobileMenuOpen(false)} />
            </div>

            {/* Overlay for mobile */}
            {isMobileMenuOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-30 md:hidden backdrop-blur-sm transition-opacity"
                    onClick={() => setIsMobileMenuOpen(false)}
                />
            )}

            {/* Main Content Area */}
            <main className="flex-1 overflow-x-hidden overflow-y-auto bg-transparent print:ml-0 p-4 pt-16 md:p-6 transition-all print:p-0 print:overflow-visible">
                {children}
            </main>
        </div>
    );
};

export default DashboardLayout;
