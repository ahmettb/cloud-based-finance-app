import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import { useNavigate } from 'react-router-dom';
import { useToast } from '../context/ToastContext';

const Login = () => {
    const [isLogin, setIsLogin] = useState(true);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const { login } = useAuth();
    const navigate = useNavigate();
    const toast = useToast();

    const [formData, setFormData] = useState({
        email: '',
        password: '',
        full_name: ''
    });

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            if (isLogin) {
                await login(formData.email, formData.password);
                toast.show.success('Giriş başarılı');
                navigate('/');
            } else {
                await api.register(formData.email, formData.password, formData.full_name);
                toast.show.success('Kayıt başarılı! Lütfen giriş yapın.');
                setIsLogin(true);
            }
        } catch (err) {
            const msg = err.message || 'Bir hata oluştu.';
            setError(msg);
            toast.show.error(msg);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-background-light dark:bg-slate-900 flex items-center justify-center p-4 font-sans">
            <div className="bg-white dark:bg-slate-800 w-full max-w-md p-8 rounded-2xl shadow-xl border border-slate-100 dark:border-slate-700">
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 text-primary mb-4">
                        <span className="material-icons-round text-4xl">query_stats</span>
                    </div>
                    <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white">FinAI'a Hoş Geldiniz</h1>
                    <p className="text-slate-500 mt-2 text-sm">Finansal özgürlüğünüze giden akıllı yol.</p>
                </div>

                {error && (
                    <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-xl text-sm font-medium border border-red-100 flex items-center gap-2">
                        <span className="material-icons-round text-sm">error</span> {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-5">
                    {!isLogin && (
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Ad Soyad</label>
                            <input
                                type="text"
                                required
                                className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none transition-all font-medium"
                                placeholder="Örn: Ahmet Yılmaz"
                                value={formData.full_name}
                                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                            />
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">E-posta Adresi</label>
                        <input
                            type="email"
                            required
                            className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none transition-all font-medium"
                            placeholder="siz@sirket.com"
                            value={formData.email}
                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Şifre</label>
                        <input
                            type="password"
                            required
                            className="w-full px-4 py-3 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 focus:ring-2 focus:ring-primary/50 outline-none transition-all font-medium"
                            placeholder="••••••••"
                            value={formData.password}
                            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full bg-primary hover:bg-primary-dark text-white font-bold py-3.5 rounded-xl shadow-lg shadow-primary/25 transition-all active:scale-[0.98] disabled:opacity-70 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                        {loading && <span className="material-icons-round animate-spin text-sm">refresh</span>}
                        {isLogin ? 'Giriş Yap' : 'Hesap Oluştur'}
                    </button>
                </form>

                <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-700 text-center">
                    <p className="text-sm text-slate-500">
                        {isLogin ? "Hesabınız yok mu?" : "Zaten üye misiniz?"}{" "}
                        <button
                            onClick={() => setIsLogin(!isLogin)}
                            className="text-primary font-bold hover:underline transition-all"
                        >
                            {isLogin ? "Kayıt Olun" : "Giriş Yapın"}
                        </button>
                    </p>
                </div>
            </div>
        </div>
    );
};

export default Login;
