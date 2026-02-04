/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                primary: "#0f172a",
                secondary: "#334155",
                accent: "#3b82f6",
            }
        },
    },
    darkMode: 'class',
    plugins: [],
}
