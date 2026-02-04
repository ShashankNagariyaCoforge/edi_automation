import { useState, useRef, useEffect } from 'react';
import { Send, Sparkles, Bot, ChevronRight, BrainCircuit } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface CopilotPanelProps {
    isOpen: boolean;
    onClose: () => void;
    sessionId: string;
    onActionComplete?: () => void;
}

interface Message {
    role: 'user' | 'assistant';
    content: string;
    thoughts?: string[];
    isThinking?: boolean;
    isReasoningCollapsed?: boolean;
}

export function CopilotPanel({ isOpen, onClose, sessionId, onActionComplete }: CopilotPanelProps) {
    const [messages, setMessages] = useState<Message[]>([
        {
            role: 'assistant',
            content: "Hello! I am your EDI Copilot. I can help you validate mappings, check the Vendor Spec, or explain X12 segments. How can I help?"
        }
    ]);
    const [input, setInput] = useState('');
    const [isProcessing, setIsProcessing] = useState(false);

    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const handleSend = async () => {
        if (!input.trim() || isProcessing) return;

        const userMsg = input;
        setInput('');
        setIsProcessing(true);

        // Add User Message
        setMessages(prev => [...prev, { role: 'user', content: userMsg }]);

        // Add Placeholder Assistant Message
        // Default reasoning to expanded (collapsed=false)
        setMessages(prev => [...prev, {
            role: 'assistant',
            content: "",
            thoughts: [],
            isThinking: true,
            isReasoningCollapsed: false
        }]);

        try {
            const response = await fetch(`http://${window.location.hostname}:8001/api/chat/${sessionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: userMsg })
            });

            if (!response.body) throw new Error("No response body");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            let currentThoughts: string[] = [];
            let currentContent = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                // Backend yields json strings. They might come concatenated.
                // We need to parse them.
                // Simple heuristic split by "}{" if multiple JSONs come in one chunk?
                // Actually backend yields line by line usually or just concatenated strings.
                // Let's rely on backend strictly sending one JSON per write if possible, 
                // but robustly we should buffer.

                // For this demo, let's assume clean chunks or simple splitting
                const lines = chunk.split('}{').join('}\n{').split('\n'); // naive fix for glued jsons

                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const event = JSON.parse(line);

                        setMessages(prev => {
                            const last = prev[prev.length - 1];
                            if (last.role !== 'assistant') return prev;

                            if (event.type === 'thought') {
                                const newThoughts = [...(last.thoughts || []), event.content];
                                return [
                                    ...prev.slice(0, -1),
                                    { ...last, thoughts: newThoughts }
                                ];
                            } else if (event.type === 'message' || event.type === 'answer') {
                                // First time receiving message/answer? Collapse thoughts.
                                const isFirstAnswerChunk = !last.content;

                                return [
                                    ...prev.slice(0, -1),
                                    {
                                        ...last,
                                        content: last.content + event.content,
                                        isThinking: false,
                                        isReasoningCollapsed: isFirstAnswerChunk ? true : last.isReasoningCollapsed
                                    }
                                ];
                            }
                            return prev;
                        });
                    } catch (e) {
                        console.log("Stream Parse Error", e, line);
                    }
                }
            }

            // Interaction complete. Trigger refresh.
            if (onActionComplete) {
                onActionComplete();
            }

        } catch (e) {
            console.error(e);
            setMessages(prev => [
                ...prev.slice(0, -1),
                { role: 'assistant', content: "Sorry, I encountered an error connecting to the Agent." }
            ]);
        } finally {
            setIsProcessing(false);

            // Cleanup "isThinking" state just in case
            setMessages(prev => {
                const last = prev[prev.length - 1];
                if (last.role === 'assistant' && last.isThinking) {
                    return [...prev.slice(0, -1), { ...last, isThinking: false }];
                }
                return prev;
            });
        }
    };

    const toggleCollapse = (index: number) => {
        setMessages(prev => prev.map((msg, i) =>
            i === index ? { ...msg, isReasoningCollapsed: !msg.isReasoningCollapsed } : msg
        ));
    };

    return (
        <AnimatePresence>
            {isOpen && (
                <motion.div
                    initial={{ x: "100%" }}
                    animate={{ x: 0 }}
                    exit={{ x: "100%" }}
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-white dark:bg-[#0f172a] shadow-2xl border-l border-slate-200 dark:border-white/10 flex flex-col"
                >
                    {/* Header */}
                    <div className="p-4 border-b border-slate-200 dark:border-white/10 flex items-center justify-between bg-white/50 dark:bg-white/5 backdrop-blur-md">
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center text-white shadow-lg">
                                <Bot className="w-5 h-5" />
                            </div>
                            <div>
                                <h3 className="font-bold text-slate-900 dark:text-white">EDI Copilot</h3>
                                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold text-emerald-500">
                                    <span className="relative flex h-2 w-2">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                                    </span>
                                    Agent Active
                                </div>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="p-2 hover:bg-slate-100 dark:hover:bg-white/10 rounded-full transition-colors"
                        >
                            <ChevronRight className="w-5 h-5 text-slate-500" />
                        </button>
                    </div>

                    {/* Messages Area */}
                    <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-6 bg-slate-50 dark:bg-transparent">
                        {messages.map((msg, i) => (
                            <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>

                                {/* Thoughts Section */}
                                {msg.role === 'assistant' && msg.thoughts && msg.thoughts.length > 0 && (
                                    <div className="mb-2 max-w-[90%] w-full transition-all duration-300">
                                        <div className="bg-slate-100 dark:bg-white/5 rounded-xl border border-slate-200 dark:border-white/5 overflow-hidden text-xs">
                                            <button
                                                onClick={() => toggleCollapse(i)}
                                                className="w-full px-3 py-2 bg-slate-200/50 dark:bg-white/5 flex items-center justify-between gap-2 text-slate-500 font-bold uppercase tracking-wider text-[10px] hover:bg-slate-200 dark:hover:bg-white/10 transition-colors"
                                            >
                                                <div className="flex items-center gap-2">
                                                    <BrainCircuit className="w-3 h-3" />
                                                    Reasoning Process
                                                </div>
                                                <ChevronRight className={`w-3 h-3 transition-transform ${!msg.isReasoningCollapsed ? 'rotate-90' : ''}`} />
                                            </button>

                                            {!msg.isReasoningCollapsed && (
                                                <motion.div
                                                    initial={{ height: 0, opacity: 0 }}
                                                    animate={{ height: "auto", opacity: 1 }}
                                                    exit={{ height: 0, opacity: 0 }}
                                                    className="p-3 font-mono text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-wrap border-t border-slate-200 dark:border-white/5"
                                                >
                                                    {msg.thoughts.join('')}
                                                    {msg.isThinking && (
                                                        <span className="inline-flex gap-1 ml-2 align-baseline">
                                                            <span className="w-1 h-1 bg-slate-400 rounded-full animate-bounce"></span>
                                                            <span className="w-1 h-1 bg-slate-400 rounded-full animate-bounce delay-75"></span>
                                                            <span className="w-1 h-1 bg-slate-400 rounded-full animate-bounce delay-150"></span>
                                                        </span>
                                                    )}
                                                </motion.div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {/* Main Content */}
                                {(msg.content || (msg.isThinking && (!msg.thoughts || msg.thoughts.length === 0))) && (
                                    <div
                                        className={`max-w-[85%] p-4 rounded-2xl shadow-sm text-sm leading-relaxed ${msg.role === 'user'
                                            ? 'bg-blue-600 text-white rounded-br-sm'
                                            : 'bg-white dark:bg-[#1e293b] border border-slate-200 dark:border-white/10 text-slate-800 dark:text-slate-200 rounded-bl-sm'
                                            }`}
                                    >
                                        {msg.content}
                                        {msg.role === 'assistant' && !msg.content && msg.isThinking && (
                                            <div className="flex gap-1 px-2">
                                                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"></span>
                                                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce delay-75"></span>
                                                <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce delay-150"></span>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Input Area */}
                    <div className="p-4 bg-white dark:bg-[#0f172a] border-t border-slate-200 dark:border-white/10">
                        <div className="relative">
                            <input
                                type="text"
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                onKeyDown={e => e.key === 'Enter' && handleSend()}
                                placeholder="Ask Copilot..."
                                disabled={isProcessing}
                                className="w-full pl-4 pr-12 py-3.5 bg-slate-100 dark:bg-[#1e293b] border-transparent focus:bg-white dark:focus:bg-[#1e293b] border focus:border-violet-500 rounded-xl outline-none transition-all text-sm disabled:opacity-50"
                            />
                            <button
                                onClick={handleSend}
                                disabled={!input.trim() || isProcessing}
                                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-0 transition-all shadow-lg shadow-violet-500/20"
                            >
                                {isProcessing ? (
                                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                                ) : (
                                    <Send className="w-4 h-4" />
                                )}
                            </button>
                        </div>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
