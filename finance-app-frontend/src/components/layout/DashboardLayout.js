import React from 'react';
import Sidebar from './Sidebar';

const DashboardLayout = ({ children }) => {
    return (
        <div className="flex h-screen bg-transparent text-slate-900 dark:text-slate-100 font-display">
            {/* Sidebar */}
            <div className="print:hidden">
                <Sidebar />
            </div>

            {/* Main Content Area */}
            <main className="flex-1 overflow-x-hidden overflow-y-auto bg-transparent md:ml-64 print:ml-0 p-4 md:p-6 transition-all print:p-0 print:overflow-visible">
                {children}
            </main>
        </div>
    );
};

export default DashboardLayout;
