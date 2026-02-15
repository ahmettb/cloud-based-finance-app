import React from 'react';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer
} from 'recharts';

const formatCurrency = (value) =>
    new Intl.NumberFormat('tr-TR', {
        style: 'currency',
        currency: 'TRY',
        maximumFractionDigits: 0
    }).format(Number(value || 0));

const CategoryTrendChart = ({ data }) => {
    // Data format: [{ date_label: '2024-05', category_name: 'Gıda', total: 150 }, ...]
    // Need to pivot this to: [{ date: '2024-05', 'Gıda': 150, 'Ulaşım': 50 }, ...]

    if (!data || data.length === 0) {
        return (
            <div className="h-full flex items-center justify-center text-xs text-slate-400 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                <span className="material-icons-round mr-2 text-base">bar_chart</span>
                Kategorik veri yok
            </div>
        );
    }

    // 1. Get unique dates and categories
    const dates = [...new Set(data.map(d => d.date_label))];
    const categories = [...new Set(data.map(d => d.category_name))];

    // 2. Pivot data
    const chartData = dates.map(date => {
        const row = { name: date };
        categories.forEach(cat => {
            const record = data.find(d => d.date_label === date && d.category_name === cat);
            row[cat] = record ? Number(record.total) : 0;
        });
        return row;
    });

    // 3. Define colors
    const colors = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#8b5cf6', '#ec4899', '#64748b'];

    const CustomTooltip = ({ active, payload, label }) => {
        if (!active || !payload || payload.length === 0) return null;
        return (
            <div className="rounded-lg border border-slate-100 bg-white px-3 py-2 shadow-xl text-xs z-50">
                <p className="font-bold text-slate-500 mb-1">{label}</p>
                {payload.map((p, i) => (
                    <div key={i} className="flex items-center gap-2 mb-0.5">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }}></div>
                        <span className="text-slate-500 w-20 truncate">{p.name}</span>
                        <span className="font-bold text-slate-800">{formatCurrency(p.value)}</span>
                    </div>
                ))}
            </div>
        );
    };

    return (
        <div className="h-full w-full">
            <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis
                        dataKey="name"
                        tick={{ fill: '#94a3b8', fontSize: 10 }}
                        tickLine={false}
                        axisLine={false}
                    />
                    <YAxis
                        tickFormatter={(val) => new Intl.NumberFormat('tr-TR', { notation: 'compact', compactDisplay: 'short' }).format(val)}
                        tick={{ fill: '#94a3b8', fontSize: 10 }}
                        tickLine={false}
                        axisLine={false}
                    />
                    <Tooltip content={<CustomTooltip />} cursor={{ fill: '#f8fafc' }} />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: '10px', paddingTop: '10px' }} />

                    {categories.map((cat, index) => (
                        <Bar
                            key={cat}
                            dataKey={cat}
                            stackId="a"
                            fill={colors[index % colors.length]}
                            radius={index === categories.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                            maxBarSize={50}
                        />
                    ))}
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
};

export default CategoryTrendChart;
