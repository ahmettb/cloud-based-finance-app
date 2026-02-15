import React, { createContext, useContext, useState, useEffect } from 'react';

const ToastContext = createContext();

export const useToast = () => useContext(ToastContext);

export const ToastProvider = ({ children }) => {
    const [toasts, setToasts] = useState([]);

    const addToast = (message, type = 'info', duration = 3000) => {
        const id = Date.now();
        setToasts(prev => [...prev, { id, message, type }]);

        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, duration);
    };

    const removeToast = (id) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    };

    const show = {
        success: (msg, duration) => addToast(msg, 'success', duration),
        error: (msg, duration) => addToast(msg, 'error', duration),
        info: (msg, duration) => addToast(msg, 'info', duration),
        warning: (msg, duration) => addToast(msg, 'warning', duration),
    };

    return (
        <ToastContext.Provider value={{ show }}>
            {children}
            <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 p-4 pointer-events-none">
                {toasts.map(toast => (
                    <ToastItem key={toast.id} {...toast} onClose={() => removeToast(toast.id)} />
                ))}
            </div>
        </ToastContext.Provider>
    );
};

const ToastItem = ({ message, type, onClose }) => {
    useEffect(() => {
        // Simple entrance animation trigger if needed
    }, []);

    const styles = {
        success: 'bg-emerald-500 text-white shadow-emerald-200',
        error: 'bg-red-500 text-white shadow-red-200',
        warning: 'bg-amber-500 text-white shadow-amber-200',
        info: 'bg-indigo-500 text-white shadow-indigo-200',
    };

    const icons = {
        success: 'check_circle',
        error: 'error',
        warning: 'warning',
        info: 'info',
    };

    return (
        <div className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg transform transition-all duration-300 animate-slide-in min-w-[300px] ${styles[type] || styles.info}`}>
            <span className="material-icons-round text-xl">{icons[type]}</span>
            <p className="font-medium text-sm flex-1">{message}</p>
            <button onClick={onClose} className="p-1 hover:bg-white/20 rounded-full transition-colors">
                <span className="material-icons-round text-sm">close</span>
            </button>
        </div>
    );
};
