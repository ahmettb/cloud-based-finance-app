import React from 'react';
import {
    Area,
    AreaChart,
    CartesianGrid,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis
} from 'recharts';

const formatCurrency = (value) =>
    new Intl.NumberFormat('tr-TR', {
        style: 'currency',
        currency: 'TRY',
        maximumFractionDigits: 0
    }).format(Number(value || 0));

const formatDateLabel = (value) => {
    if (!value) return '';
    try {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value; // Fallback if not date

        // If YYYY-MM format (length 7), show Month Year
        if (value.length === 7) {
            return date.toLocaleDateString('tr-TR', { month: 'short', year: '2-digit' });
        }
        // If YYYY-MM-DD format, show Day Month
        return date.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short' });
    } catch (e) {
        return value;
    }
};

const SpendingChart = ({ data }) => {
    // Adapter for old format: { months: [], datasets: [] } -> [{ date_label, total }]
    let chartData = [];
    if (data && data.months && Array.isArray(data.months)) {
        chartData = data.months.map((month, index) => {
            const total = (data.datasets || []).reduce((sum, dataset) => sum + Number(dataset?.data?.[index] || 0), 0);
            return { date_label: month, total };
        });
    } else if (Array.isArray(data)) {
        // New format directly
        chartData = data.map(item => ({
            ...item,
            total: Number(item.total || 0)
        }));
    }

    if (!chartData || chartData.length === 0) {
        return (
            <div className="h-full flex items-center justify-center text-xs text-slate-400 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                <span className="material-icons-round mr-2 text-base">sentiment_dissatisfied</span>
                Grafik verisi yok
            </div>
        );
    }

    const CustomTooltip = ({ active, payload, label }) => {
        if (!active || !payload || payload.length === 0) return null;
        return (
            <div className="rounded-lg border border-slate-100 bg-white px-3 py-2 shadow-xl text-xs z-50">
                <p className="font-bold text-slate-500 mb-1">{formatDateLabel(label)}</p>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-indigo-500"></div>
                    <p className="font-bold text-slate-800 text-sm">{formatCurrency(payload[0].value)}</p>
                </div>
            </div>
        );
    };

    return (
        <div className="h-full w-full">
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                        <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis
                        dataKey="date_label"
                        tickFormatter={formatDateLabel}
                        tick={{ fill: '#94a3b8', fontSize: 10 }}
                        tickLine={false}
                        axisLine={false}
                        minTickGap={30}
                    />
                    <YAxis
                        tickFormatter={(val) => new Intl.NumberFormat('tr-TR', { notation: 'compact', compactDisplay: 'short' }).format(val)}
                        tick={{ fill: '#94a3b8', fontSize: 10 }}
                        tickLine={false}
                        axisLine={false}
                    />
                    <Tooltip content={<CustomTooltip />} cursor={{ stroke: '#cbd5e1', strokeWidth: 1, strokeDasharray: '4 4' }} />
                    <Area
                        type="monotone"
                        dataKey="total"
                        stroke="#6366f1"
                        strokeWidth={2}
                        fillOpacity={1}
                        fill="url(#colorTotal)"
                        animationDuration={1000}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
};

export default SpendingChart;
