import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

const VoiceExpenseWizard = ({ onSave, onClose }) => {
    const toast = useToast();
    const [isListening, setIsListening] = useState(false);
    const [transcript, setTranscript] = useState('');
    const [analyzing, setAnalyzing] = useState(false);
    const [result, setResult] = useState(null); // { merchant, amount, category, date, description }

    // Web Speech API Ref
    const recognitionRef = useRef(null);

    useEffect(() => {
        // Initialize Web Speech API
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognitionRef.current = new SpeechRecognition();
            recognitionRef.current.continuous = true;
            recognitionRef.current.interimResults = true;
            recognitionRef.current.lang = 'tr-TR';

            recognitionRef.current.onresult = (event) => {
                let interm = '';
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    if (event.results[i].isFinal) {
                        setTranscript(prev => prev + ' ' + event.results[i][0].transcript);
                    } else {
                        interm += event.results[i][0].transcript;
                    }
                }
            };

            recognitionRef.current.onerror = (event) => {
                console.error("Speech Error:", event.error);
                setIsListening(false);
                toast.show.error("Ses algılanamadı.");
            };

            recognitionRef.current.onend = () => {
                setIsListening(false);
            };
        } else {
            toast.show.error("Tarayıcınız sesli komutu desteklemiyor.");
        }
    }, []);

    const toggleListening = () => {
        if (isListening) {
            recognitionRef.current?.stop();
            setIsListening(false);
        } else {
            setTranscript('');
            setResult(null);
            recognitionRef.current?.start();
            setIsListening(true);
        }
    };

    const handleAnalyze = async () => {
        if (!transcript.trim()) {
            toast.show.warning("Lütfen önce konuşun veya bir şeyler yazın.");
            return;
        }

        setAnalyzing(true);
        try {
            const data = await api.extractSmartData(transcript);
            setResult(data);
            setIsListening(false);
            recognitionRef.current?.stop();
        } catch (error) {
            console.error("Analysis failed", error);
            toast.show.error("Analiz başarısız oldu.");
        } finally {
            setAnalyzing(false);
        }
    };

    const handleSave = async () => {
        if (!result) return;
        try {
            await api.createManualExpense(result);
            toast.show.success("Harcama kaydedildi!");
            onSave(); // Refresh dashboard
            onClose();
        } catch (error) {
            console.error(error);
            toast.show.error("Kaydetme hatası.");
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
            <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl w-full max-w-lg border border-slate-200 dark:border-slate-800 overflow-hidden flex flex-col max-h-[90vh]">

                {/* Header */}
                <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-indigo-50 dark:bg-slate-800/50">
                    <h3 className="font-bold text-indigo-900 dark:text-white flex items-center gap-2">
                        <span className="material-icons-round text-indigo-500">mic</span>
                        Akıllı Sesli Asistan
                    </h3>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
                        <span className="material-icons-round">close</span>
                    </button>
                </div>

                <div className="p-6 overflow-y-auto flex-1">
                    {!result ? (
                        <div className="flex flex-col items-center justify-center space-y-6 py-8">
                            <div className={`relative w-24 h-24 rounded-full flex items-center justify-center transition-all duration-300 ${isListening ? 'bg-red-50 scale-110 shadow-red-200 shadow-xl' : 'bg-slate-50'}`}>
                                <button
                                    onClick={toggleListening}
                                    className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${isListening ? 'bg-red-500 animate-pulse' : 'bg-indigo-600 hover:bg-indigo-700'} text-white shadow-lg`}
                                >
                                    <span className="material-icons-round text-4xl">{isListening ? 'stop' : 'mic'}</span>
                                </button>
                                {isListening && (
                                    <div className="absolute inset-0 rounded-full border-4 border-red-500 opacity-20 animate-ping"></div>
                                )}
                            </div>

                            <p className="text-center text-slate-500 text-sm max-w-xs">
                                {isListening ? "Dinliyorum..." : "Mikrofona basıp konuşun. Örn: 'Dün akşam markette 350 lira harcadım'"}
                            </p>

                            <div className="w-full">
                                <textarea
                                    value={transcript}
                                    onChange={(e) => setTranscript(e.target.value)}
                                    placeholder="Veya buraya yazabilirsiniz..."
                                    className="w-full p-4 rounded-xl bg-slate-50 dark:bg-slate-800 border-none outline-none focus:ring-2 focus:ring-indigo-500/20 text-slate-800 dark:text-white font-medium text-lg resize-none text-center"
                                    rows="3"
                                />
                            </div>

                            <button
                                onClick={handleAnalyze}
                                disabled={!transcript || analyzing}
                                className="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold py-3 rounded-xl disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {analyzing ? <span className="material-icons-round animate-spin">refresh</span> : <span className="material-icons-round">auto_awesome</span>}
                                {analyzing ? 'Analiz Ediliyor...' : 'Analiz Et'}
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            <div className="bg-emerald-50 border border-emerald-100 p-4 rounded-xl flex items-start gap-3">
                                <span className="material-icons-round text-emerald-600 mt-1">check_circle</span>
                                <div>
                                    <p className="text-emerald-800 font-bold text-sm">Analiz Başarılı!</p>
                                    <p className="text-emerald-600 text-xs">Lütfen bilgileri kontrol edip onaylayın.</p>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-xs font-bold text-slate-500 uppercase">Yer / Satıcı</label>
                                    <input
                                        type="text"
                                        value={result.merchant_name}
                                        onChange={e => setResult({ ...result, merchant_name: e.target.value })}
                                        className="w-full p-2 bg-slate-50 rounded-lg border border-slate-200 text-sm font-bold"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-bold text-slate-500 uppercase">Tutar</label>
                                    <input
                                        type="number"
                                        value={result.total_amount}
                                        onChange={e => setResult({ ...result, total_amount: e.target.value })}
                                        className="w-full p-2 bg-slate-50 rounded-lg border border-slate-200 text-sm font-bold"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-bold text-slate-500 uppercase">Kategori</label>
                                    <input
                                        type="text"
                                        value={result.category_name}
                                        onChange={e => setResult({ ...result, category_name: e.target.value })}
                                        className="w-full p-2 bg-slate-50 rounded-lg border border-slate-200 text-sm font-medium"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-bold text-slate-500 uppercase">Tarih</label>
                                    <input
                                        type="date"
                                        value={result.receipt_date}
                                        onChange={e => setResult({ ...result, receipt_date: e.target.value })}
                                        className="w-full p-2 bg-slate-50 rounded-lg border border-slate-200 text-sm font-medium"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="text-xs font-bold text-slate-500 uppercase">Açıklama</label>
                                <textarea
                                    value={result.description || ''}
                                    onChange={e => setResult({ ...result, description: e.target.value })}
                                    className="w-full p-2 bg-slate-50 rounded-lg border border-slate-200 text-sm font-medium resize-none"
                                    rows="2"
                                />
                            </div>

                            <div className="flex gap-3 pt-4">
                                <button
                                    onClick={() => setResult(null)}
                                    className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold py-3 rounded-xl transition-colors"
                                >
                                    Düzenle / Tekrar
                                </button>
                                <button
                                    onClick={handleSave}
                                    className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 rounded-xl shadow-lg shadow-indigo-200 transition-colors flex justify-center items-center gap-2"
                                >
                                    <span className="material-icons-round">save</span>
                                    Onayla ve Kaydet
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default VoiceExpenseWizard;
