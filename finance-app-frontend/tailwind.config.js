/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./src/**/*.{js,jsx,ts,tsx}",
    ],
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                "primary": "#477eeb",
                "primary-dark": "#3b6ac8",
                "background-light": "#f6f6f8",
                "background-dark": "#111621",
                "accent-green": "#10b981",
                "accent-amber": "#f59e0b",
                "accent-red": "#ef4444",
                "accent-purple": "#8b5cf6",
            },
            fontFamily: {
                "display": ["Manrope", "sans-serif"],
                "sans": ["Manrope", "sans-serif"]
            },
        },
    },
    plugins: [],
}
