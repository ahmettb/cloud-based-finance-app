import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { api } from '../services/api';
import { useNavigate } from 'react-router-dom';
import { useToast } from '../context/ToastContext';

const Login = () => {
    const [isLogin, setIsLogin] = useState(true);
    const [isConfirming, setIsConfirming] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const { login } = useAuth();
    const navigate = useNavigate();
    const toast = useToast();

    const [formData, setFormData] = useState({
        email: '',
        password: '',
        full_name: '',
        code: ''
    });

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            if (isConfirming) {
                await api.confirm(formData.email, formData.code);
                toast.show.success('Hesabınız doğrulandı! Lütfen giriş yapın.');
                setIsConfirming(false);
                setIsLogin(true);
            } else if (isLogin) {
                await login(formData.email, formData.password);
                toast.show.success('Giriş başarılı');
                navigate('/');
            } else {
                await api.register(formData.email, formData.password, formData.full_name);
                toast.show.success('Kayıt başarılı! Lütfen e-postanıza gelen kodu girin.');
                setIsConfirming(true);
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
        <div className="flex min-h-screen bg-slate-50 dark:bg-slate-900 font-sans">
            {/* Left Side - Auth Form */}
            <div className="w-full lg:w-1/2 flex items-center justify-center p-8 sm:p-12">
                <div className="w-full mx-auto max-w-sm">
                    {/* Logo Area */}
                    <div className="flex items-center gap-3 mb-10">
                        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-primary text-white shadow-lg shadow-primary/30">
                            <span className="material-icons-round text-2xl">account_balance_wallet</span>
                        </div>
                        <div>
                            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">ParamNerede</h1>
                            <p className="text-xs font-medium text-slate-500">Akıllı Finans Asistanı</p>
                        </div>
                    </div>

                    <div className="mb-8">
                        <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight mb-2">
                            {isConfirming ? 'Hesabınızı Doğrulayın' : isLogin ? 'Tekrar Hoş Geldiniz' : 'Hesap Oluşturun'}
                        </h2>
                        <p className="text-slate-500 text-sm font-medium">
                            {isConfirming
                                ? 'E-postanıza gönderdiğimiz doğrulama kodunu girin.'
                                : isLogin
                                    ? 'Finansal kontrolünüzü elinize almak için giriş yapın.'
                                    : 'Dakikalar içinde ParamNerede dünyasına katılın.'}
                        </p>
                    </div>

                    {error && (
                        <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-xl text-sm font-medium border border-red-100 flex items-center gap-2">
                            <span className="material-icons-round text-sm">error</span> {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-5">
                        {isConfirming ? (
                            <>
                                <div>
                                    <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">E-posta Adresi</label>
                                    <input
                                        type="email"
                                        disabled
                                        className="w-full px-4 py-3 rounded-xl bg-slate-100/50 dark:bg-slate-800 border-none ring-1 ring-slate-200 dark:ring-slate-700 font-medium text-slate-500 cursor-not-allowed"
                                        value={formData.email}
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Doğrulama Kodu</label>
                                    <input
                                        type="text"
                                        required
                                        className="w-full px-4 py-3 rounded-xl bg-white dark:bg-slate-900 border-none ring-1 ring-slate-200 dark:ring-slate-700 focus:ring-2 focus:ring-primary outline-none transition-all font-medium"
                                        placeholder="Örn: 123456"
                                        value={formData.code}
                                        onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                    />
                                </div>
                            </>
                        ) : (
                            <>
                                {!isLogin && (
                                    <div>
                                        <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Ad Soyad</label>
                                        <input
                                            type="text"
                                            required
                                            className="w-full px-4 py-3 rounded-xl bg-white dark:bg-slate-900 border-none ring-1 ring-slate-200 dark:ring-slate-700 focus:ring-2 focus:ring-primary outline-none transition-all font-medium"
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
                                        className="w-full px-4 py-3 rounded-xl bg-white dark:bg-slate-900 border-none ring-1 ring-slate-200 dark:ring-slate-700 focus:ring-2 focus:ring-primary outline-none transition-all font-medium"
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
                                        className="w-full px-4 py-3 rounded-xl bg-white dark:bg-slate-900 border-none ring-1 ring-slate-200 dark:ring-slate-700 focus:ring-2 focus:ring-primary outline-none transition-all font-medium"
                                        placeholder="••••••••"
                                        value={formData.password}
                                        onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                    />
                                </div>
                            </>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full mt-2 bg-primary hover:bg-primary-dark text-white font-bold py-3.5 rounded-xl shadow-lg shadow-primary/25 transition-all active:scale-[0.98] disabled:opacity-70 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        >
                            {loading && <span className="material-icons-round animate-spin text-sm">refresh</span>}
                            {isConfirming ? 'Hesabımı Doğrula' : isLogin ? 'Giriş Yap' : 'Ücretsiz Kayıt Ol'}
                        </button>
                    </form>

                    {!isConfirming && (
                        <div className="mt-8 text-center text-sm font-medium text-slate-500">
                            {isLogin ? "Henüz ParamNerede kullanmıyor musunuz?" : "Zaten bir hesabınız var mı?"}{" "}
                            <button
                                onClick={() => setIsLogin(!isLogin)}
                                className="text-primary font-bold hover:text-primary-dark underline decoration-2 underline-offset-4 transition-colors ml-1"
                            >
                                {isLogin ? "Kayıt Olun" : "Giriş Yapın"}
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* Right Side - Features/Info Banner */}
            <div className="hidden lg:flex lg:w-1/2 p-4">
                <div className="relative w-full h-full bg-slate-900 rounded-3xl overflow-hidden flex flex-col p-12 justify-between">
                    {/* Decorative Elements */}
                    <div className="absolute top-0 right-0 w-96 h-96 bg-primary/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3"></div>
                    <div className="absolute bottom-0 left-0 w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl translate-y-1/2 -translate-x-1/3"></div>

                    <div className="relative z-10 flex items-center gap-3">
                        <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></div>
                        <span className="text-slate-300 font-medium tracking-wide">AI Destekli Yeni Nesil Finans</span>
                    </div>

                    <div className="relative z-10">
                        <h2 className="text-5xl font-extrabold text-white leading-[1.1] mb-6">
                            Geleceğinize <br /><span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-indigo-400">Yatırım Yapın</span>
                        </h2>

                        <div className="space-y-6 max-w-md">
                            <div className="flex gap-4 items-start">
                                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center border border-slate-700">
                                    <span className="material-icons-round text-primary text-xl">receipt_long</span>
                                </div>
                                <div>
                                    <h3 className="text-white font-bold mb-1">OCR Fiş Tarama</h3>
                                    <p className="text-slate-400 text-sm">Harcamalarınızı tek tuşla sisteme aktarın. Yapay zeka fişinizi otomatik okusun.</p>
                                </div>
                            </div>
                            <div className="flex gap-4 items-start">
                                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center border border-slate-700">
                                    <span className="material-icons-round text-indigo-400 text-xl">auto_awesome</span>
                                </div>
                                <div>
                                    <h3 className="text-white font-bold mb-1">Akıllı Bütçe Asistanı</h3>
                                    <p className="text-slate-400 text-sm">Harcama kalıplarınızı analiz edip, size özel tasarruf tavsiyeleri edinin.</p>
                                </div>
                            </div>
                            <div className="flex gap-4 items-start">
                                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center border border-slate-700">
                                    <span className="material-icons-round text-emerald-400 text-xl">insights</span>
                                </div>
                                <div>
                                    <h3 className="text-white font-bold mb-1">Gelecek Tahminleri</h3>
                                    <p className="text-slate-400 text-sm">Geçmiş verilerinize dayanarak önümüzdeki aylardaki durumunuzu öngörün.</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Footer for Right Side */}
                    <div className="relative z-10 flex items-center justify-between pt-12 border-t border-slate-800">
                        <p className="text-slate-400 font-medium">© 2026 ParamNerede.</p>
                        <div className="flex -space-x-2">
                            {/* Dummy avatars for social proof */}
                            <div className="w-10 h-10 rounded-full bg-slate-700 border-2 border-slate-900 flex items-center justify-center"><span className="material-icons-round text-sm text-white">person</span></div>
                            <div className="w-10 h-10 rounded-full bg-slate-600 border-2 border-slate-900 flex items-center justify-center"><span className="material-icons-round text-sm text-white">face</span></div>
                            <div className="w-10 h-10 rounded-full bg-slate-800 border-2 border-slate-900 flex items-center justify-center"><span className="text-xs text-white font-bold">+10k</span></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Login;
