import React, { useState, useRef, useEffect } from 'react';
import DashboardLayout from '../components/layout/DashboardLayout';
import { api } from '../services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const AIChat = () => {
    const [messages, setMessages] = useState([
        {
            id: 1,
            role: 'assistant',
            content: 'Merhaba! Ben senin finansal asistanınım. Harcamaların, bütçen veya finansal durumun hakkında bana sorular sorabilirsin.\n\nÖrnek sorular:\n* Geçen ay markete ne kadar harcadım?\n* En çok hangi kategoride para harcıyorum?\n* Geçen haftaki kahve masraflarım ne kadardı?'
        }
    ]);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
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

    return (
        <DashboardLayout>
            <div className="max-w-4xl mx-auto h-[calc(100vh-6rem)] md:h-[calc(100vh-4rem)] flex flex-col bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 overflow-hidden">
                {/* Header */}
                <div className="flex-none p-4 md:p-6 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 z-10">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
                            <span className="material-icons-round text-2xl">auto_awesome</span>
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-slate-900 dark:text-white">AI Finansal Asistan</h1>
                            <p className="text-sm text-slate-500 dark:text-slate-400">Verilerinize dayalı kişiselleştirilmiş finansal sohbet</p>
                        </div>
                    </div>
                </div>

                {/* Messages Area */}
                <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-slate-50 dark:bg-slate-900/50 space-y-6">
                    {messages.map((message) => (
                        <div
                            key={message.id}
                            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div className={`flex max-w-[85%] md:max-w-[75%] ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'} gap-3 items-end`}>

                                {/* Avatar */}
                                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${message.role === 'user'
                                        ? 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                                        : message.role === 'error'
                                            ? 'bg-red-100 text-red-600'
                                            : 'bg-primary text-white'
                                    }`}>
                                    <span className="material-icons-round text-[18px]">
                                        {message.role === 'user' ? 'person' : message.role === 'error' ? 'error_outline' : 'smart_toy'}
                                    </span>
                                </div>

                                {/* Message Bubble */}
                                <div className={`px-5 py-3.5 rounded-2xl ${message.role === 'user'
                                        ? 'bg-primary text-white rounded-br-sm'
                                        : message.role === 'error'
                                            ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-bl-sm border border-red-100 dark:border-red-900/50'
                                            : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-bl-sm border border-slate-200 dark:border-slate-700 shadow-sm'
                                    }`}>
                                    <div className={`prose prose-sm md:prose-base max-w-none ${message.role === 'user'
                                            ? 'text-white prose-invert'
                                            : 'dark:prose-invert prose-p:leading-relaxed prose-li:my-1'
                                        }`}>
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                            {message.content}
                                        </ReactMarkdown>
                                    </div>

                                    {/* Context indicator for AI responses */}
                                    {message.role === 'assistant' && message.contextUsed !== undefined && (
                                        <div className="mt-2 pt-2 border-t border-slate-100 dark:border-slate-700 flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                                            <span className="material-icons-round text-[14px]">
                                                {message.contextUsed > 0 ? 'find_in_page' : 'info_outline'}
                                            </span>
                                            {message.contextUsed > 0
                                                ? `${message.contextUsed} finansal kayıt incelendi`
                                                : 'Detaylı veri bulunamadı, genel bilgi verildi'}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}

                    {/* Loading Indicator */}
                    {isLoading && (
                        <div className="flex justify-start">
                            <div className="flex gap-3 items-end">
                                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center">
                                    <span className="material-icons-round text-[18px]">smart_toy</span>
                                </div>
                                <div className="px-5 py-4 rounded-2xl bg-white dark:bg-slate-800 rounded-bl-sm border border-slate-200 dark:border-slate-700 shadow-sm shrink-0">
                                    <div className="flex gap-1.5">
                                        <div className="w-2 h-2 rounded-full bg-slate-300 dark:bg-slate-600 animate-bounce" style={{ animationDelay: '0ms' }} />
                                        <div className="w-2 h-2 rounded-full bg-slate-300 dark:bg-slate-600 animate-bounce" style={{ animationDelay: '150ms' }} />
                                        <div className="w-2 h-2 rounded-full bg-slate-300 dark:bg-slate-600 animate-bounce" style={{ animationDelay: '300ms' }} />
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>

                {/* Input Area */}
                <div className="flex-none p-4 md:p-6 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800">
                    <form
                        onSubmit={handleSendMessage}
                        className="relative flex items-end gap-2"
                    >
                        <div className="relative flex-1 bg-slate-50 dark:bg-slate-800 rounded-2xl border border-slate-300 dark:border-slate-700 focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary transition-all overflow-hidden group">
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
                                placeholder="Finansal sorularınızı buraya yazın..."
                                className="w-full max-h-32 min-h-[56px] py-4 pl-4 pr-12 bg-transparent text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none resize-none disabled:opacity-50 text-[15px] md:text-base leading-relaxed"
                                rows="1"
                            />

                            {/* Send icon inside the input area */}
                            <div className="absolute right-2 bottom-2">
                                <button
                                    type="submit"
                                    disabled={!inputValue.trim() || isLoading}
                                    className="w-10 h-10 rounded-xl flex items-center justify-center bg-primary text-white hover:bg-primary-dark disabled:bg-slate-200 disabled:text-slate-400 dark:disabled:bg-slate-700 dark:disabled:text-slate-500 transition-colors"
                                >
                                    <span className="material-icons-round text-xl">
                                        {isLoading ? 'hourglass_empty' : 'send'}
                                    </span>
                                </button>
                            </div>
                        </div>
                    </form>
                    <p className="text-center text-xs text-slate-400 dark:text-slate-500 mt-3">
                        Yapay zeka asistanı hata yapabilir. Önemli finansal kararlarınızda verilerinizi teyit edin.
                    </p>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default AIChat;
