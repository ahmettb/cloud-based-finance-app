import React, { useState, useRef, useEffect } from 'react';
import { api } from '../services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const FloatingAIChat = () => {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState(() => {
        const saved = localStorage.getItem('paramnerede_ai_chat_history');
        if (saved) {
            try {
                return JSON.parse(saved);
            } catch (e) {
                console.error("Failed to parse chat history");
            }
        }
        return [
            {
                id: 1,
                role: 'assistant',
                content: 'Merhaba! Ben senin finansal asistanınım. Harcamaların, bütçen veya finansal durumun hakkında bana sorular sorabilirsin.\n\nÖrnek sorular:\n* Geçen ay markete ne kadar harcadım?\n* En çok hangi kategoride para harcıyorum?\n* Geçen haftaki kahve masraflarım ne kadardı?'
            }
        ];
    });
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        if (isOpen) {
            scrollToBottom();
        }
    }, [messages, isOpen]);

    // Persist to localStorage whenever messages change
    useEffect(() => {
        localStorage.setItem('paramnerede_ai_chat_history', JSON.stringify(messages));
    }, [messages]);

    const handleSendMessage = async (e) => {
        e.preventDefault();

        if (!inputValue.trim() || isLoading) return;

        const userMessage = {
            id: Date.now(),
            role: 'user',
            content: inputValue.trim()
        };

        setMessages(prev => [...prev, userMessage]);
        setInputValue('');
        setIsLoading(true);

        try {
            const response = await api.sendChatQuery(userMessage.content);

            const assistantMessage = {
                id: Date.now() + 1,
                role: 'assistant',
                content: response.reply,
                contextUsed: response.context_used
            };

            setMessages(prev => [...prev, assistantMessage]);
        } catch (error) {
            const errorMessage = {
                id: Date.now() + 1,
                role: 'error',
                content: error.message || 'Üzgünüm, şu anda yanıt veremiyorum. Lütfen daha sonra tekrar deneyin.'
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleClearHistory = () => {
        if (window.confirm('Sohbet geçmişini silmek istediğinize emin misiniz?')) {
            const defaultMsg = {
                id: 1,
                role: 'assistant',
                content: 'Merhaba! Ben senin finansal asistanınım. Harcamaların, bütçen veya finansal durumun hakkında bana sorular sorabilirsin.\n\nÖrnek sorular:\n* Geçen ay markete ne kadar harcadım?\n* En çok hangi kategoride para harcıyorum?\n* Geçen haftaki kahve masraflarım ne kadardı?'
            };
            setMessages([defaultMsg]);
            localStorage.setItem('paramnerede_ai_chat_history', JSON.stringify([defaultMsg]));
        }
    };

    return (
        <div className="fixed bottom-6 right-6 z-50 animate-fade-in-up">
            {/* Chat Button */}
            {!isOpen && (
                <button
                    onClick={() => setIsOpen(true)}
                    className="w-14 h-14 rounded-full bg-primary text-white shadow-xl hover:shadow-2xl hover:scale-105 active:scale-95 transition-all flex items-center justify-center relative group"
                >
                    <span className="material-icons-round text-2xl">auto_awesome</span>

                    {/* Optional Notification Dot */}
                    <span className="absolute top-0 right-0 w-3 h-3 bg-red-500 border-2 border-white rounded-full"></span>

                    {/* Tooltip */}
                    <span className="absolute right-full mr-4 bg-slate-900 text-white text-sm px-3 py-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                        AI Asistana Sor
                    </span>
                </button>
            )}

            {/* Chat Window */}
            {isOpen && (
                <div className="w-[380px] sm:w-[420px] h-[600px] max-h-[85vh] bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 flex flex-col overflow-hidden animate-slide-up origin-bottom-right mr-2 mb-2 sm:mr-0 sm:mb-0">
                    {/* Header */}
                    <div className="flex-none p-4 border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                                <span className="material-icons-round">smart_toy</span>
                            </div>
                            <div>
                                <h3 className="font-bold text-slate-900 dark:text-white">AI Asistan</h3>
                                <p className="text-xs text-slate-500 dark:text-slate-400">Verilerinize dayalı analist</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-1 text-slate-400">
                            <button
                                onClick={handleClearHistory}
                                className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                                title="Geçmişi Temizle"
                            >
                                <span className="material-icons-round text-lg">delete_sweep</span>
                            </button>
                            <button
                                onClick={() => setIsOpen(false)}
                                className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                            >
                                <span className="material-icons-round text-lg">close</span>
                            </button>
                        </div>
                    </div>

                    {/* Messages Area */}
                    <div className="flex-1 overflow-y-auto p-4 bg-slate-50 dark:bg-slate-900/50 space-y-5">
                        {messages.map((message) => (
                            <div
                                key={message.id}
                                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                <div className={`flex max-w-[85%] ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'} gap-2.5 items-end`}>

                                    {/* Avatar */}
                                    <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${message.role === 'user'
                                            ? 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                                            : message.role === 'error'
                                                ? 'bg-red-100 text-red-600'
                                                : 'bg-primary text-white'
                                        }`}>
                                        <span className="material-icons-round text-[16px]">
                                            {message.role === 'user' ? 'person' : message.role === 'error' ? 'error_outline' : 'smart_toy'}
                                        </span>
                                    </div>

                                    {/* Message Bubble */}
                                    <div className={`px-4 py-3 rounded-2xl ${message.role === 'user'
                                            ? 'bg-primary text-white rounded-br-sm'
                                            : message.role === 'error'
                                                ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-bl-sm border border-red-100 dark:border-red-900/50'
                                                : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-bl-sm border border-slate-200 dark:border-slate-700 shadow-sm'
                                        }`}>
                                        <div className={`prose prose-sm max-w-none ${message.role === 'user'
                                                ? 'text-white prose-invert'
                                                : 'dark:prose-invert prose-p:leading-relaxed prose-li:my-1'
                                            }`}>
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {message.content}
                                            </ReactMarkdown>
                                        </div>

                                        {/* Context indicator */}
                                        {message.role === 'assistant' && message.contextUsed !== undefined && message.contextUsed > 0 && (
                                            <div className="mt-2 pt-2 border-t border-slate-100 dark:border-slate-700 flex items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500">
                                                <span className="material-icons-round text-[12px]">find_in_page</span>
                                                Kayıtlarınız tarandı
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}

                        {/* Loading Indicator */}
                        {isLoading && (
                            <div className="flex justify-start">
                                <div className="flex gap-2.5 items-end">
                                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary text-white flex items-center justify-center">
                                        <span className="material-icons-round text-[16px]">smart_toy</span>
                                    </div>
                                    <div className="px-5 py-4 rounded-2xl bg-white dark:bg-slate-800 rounded-bl-sm border border-slate-200 dark:border-slate-700 shadow-sm shrink-0">
                                        <div className="flex gap-1.5">
                                            <div className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600 animate-bounce" style={{ animationDelay: '0ms' }} />
                                            <div className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600 animate-bounce" style={{ animationDelay: '150ms' }} />
                                            <div className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600 animate-bounce" style={{ animationDelay: '300ms' }} />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}

                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input Area */}
                    <div className="flex-none p-3 bg-white dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800">
                        <form
                            onSubmit={handleSendMessage}
                            className="relative flex items-end gap-2"
                        >
                            <div className="relative flex-1 bg-slate-50 dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary transition-all overflow-hidden">
                                <textarea
                                    value={inputValue}
                                    onChange={(e) => setInputValue(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            handleSendMessage(e);
                                        }
                                    }}
                                    disabled={isLoading}
                                    placeholder="Bir şey sorun..."
                                    className="w-full max-h-24 min-h-[48px] py-3 pl-4 pr-11 bg-transparent text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none resize-none disabled:opacity-50 text-sm"
                                    rows="1"
                                />

                                <div className="absolute right-1.5 bottom-1.5">
                                    <button
                                        type="submit"
                                        disabled={!inputValue.trim() || isLoading}
                                        className="w-9 h-9 rounded-xl flex items-center justify-center bg-primary text-white hover:bg-primary-dark disabled:bg-slate-200 disabled:text-slate-400 dark:disabled:bg-slate-700 dark:disabled:text-slate-500 transition-colors"
                                    >
                                        <span className="material-icons-round text-lg">
                                            {isLoading ? 'hourglass_empty' : 'send'}
                                        </span>
                                    </button>
                                </div>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default FloatingAIChat;
