
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { motion } from 'framer-motion';

export const ThemeToggle = () => {
    const { theme, toggleTheme } = useTheme();

    return (
        <button
            onClick={toggleTheme}
            className="relative p-2 rounded-lg bg-slate-200 dark:bg-slate-800 text-slate-800 dark:text-slate-200 hover:bg-slate-300 dark:hover:bg-slate-700 transition-colors border border-slate-300 dark:border-slate-700"
            aria-label="Toggle Theme"
        >
            <div className="relative w-5 h-5">
                <motion.div
                    initial={false}
                    animate={{ scale: theme === 'light' ? 1 : 0, rotate: theme === 'light' ? 0 : 90, opacity: theme === 'light' ? 1 : 0 }}
                    transition={{ duration: 0.2 }}
                    className="absolute inset-0"
                >
                    <Sun className="w-5 h-5 text-amber-500" />
                </motion.div>
                <motion.div
                    initial={false}
                    animate={{ scale: theme === 'dark' ? 1 : 0, rotate: theme === 'dark' ? 0 : -90, opacity: theme === 'dark' ? 1 : 0 }}
                    transition={{ duration: 0.2 }}
                    className="absolute inset-0"
                >
                    <Moon className="w-5 h-5 text-indigo-400" />
                </motion.div>
            </div>
        </button>
    );
};
