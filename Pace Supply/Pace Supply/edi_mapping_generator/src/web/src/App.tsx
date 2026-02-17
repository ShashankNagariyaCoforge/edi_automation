import { useState, useMemo } from 'react';
import { FileText, CheckCircle, Download, Play, AlertCircle, ChevronLeft, Network, Package, FileSpreadsheet, Send, Bot } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { ThemeToggle } from './components/ThemeToggle';

import { CopilotPanel } from './components/CopilotPanel';

// Types
interface MappingData {
  [recordId: string]: {
    [field: string]: {
      B: string | null;
      C: string | null;
      logic: string;
      validation_warning?: string;
    }
  }
}

// 856 Mapping is simpler in structure (List) but comes over wire as "mappings": { "mappings": [...] }
// but we just use the GRID for editing.

interface AppState {
  step: 'landing' | 'upload' | 'processing' | 'review';
  flowType: '850' | '856' | 'nestle' | null;
  sessionId: string | null;
  grid: any[][] | null;
  mappings: MappingData | any | null; // Flexible for 856
  isCopilotOpen?: boolean;
  nestleFlags?: Record<number, { col: number; reason: string }>; // row_idx → flag info
}

function App() {
  const [state, setState] = useState<AppState>({
    step: 'landing',
    flowType: null,
    sessionId: null,
    grid: null,
    mappings: null,
    isCopilotOpen: false,
    nestleFlags: {}
  });

  const [files, setFiles] = useState<{ pdf: File | null }>({
    pdf: null,
  });

  const [error, setError] = useState<string | null>(null);

  // Dynamic API Base URL
  const API_BASE = `http://${window.location.hostname}:8001`;

  // Reset helper
  const reset = () => {
    setState({
      step: 'landing',
      flowType: null,
      sessionId: null,
      grid: null,
      mappings: null,
      isCopilotOpen: false,
      nestleFlags: {}
    });
    setFiles({ pdf: null });
    setError(null);
  };

  const startFlow = (type: '850' | '856' | 'nestle') => {
    setState(p => ({ ...p, flowType: type, step: 'upload' }));
    setFiles({ pdf: null }); // Clear files on switch
  };

  const handleFileUpload = async () => {
    if (!state.flowType) return;

    // Validation
    if (!files.pdf) return;

    setError(null);
    setState(prev => ({ ...prev, step: 'processing' }));

    const formData = new FormData();
    if (files.pdf) formData.append('pdf_file', files.pdf);

    try {
      let endpoint = '';
      if (state.flowType === '856') endpoint = `${API_BASE}/api/856/upload`;
      else if (state.flowType === 'nestle') endpoint = `${API_BASE}/api/nestle/upload`;
      else endpoint = `${API_BASE}/api/upload`;

      const res = await fetch(endpoint, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);

      const data = await res.json();
      setState(prev => ({ ...prev, sessionId: data.session_id }));

      // Trigger generation immediately
      await startGeneration(data.session_id);
    } catch (err: any) {
      console.error("Upload failed", err);
      setError(err.message || "An unexpected error occurred during upload.");
      setState(prev => ({ ...prev, step: 'upload' }));
    }
  };

  const startGeneration = async (sessionId: string) => {
    try {
      let endpoint = '';
      if (state.flowType === '856') endpoint = `${API_BASE}/api/856/generate/${sessionId}`;
      else if (state.flowType === 'nestle') endpoint = `${API_BASE}/api/nestle/generate/${sessionId}`;
      else endpoint = `${API_BASE}/api/generate/${sessionId}`;

      const res = await fetch(endpoint, { method: 'POST' });
      if (!res.ok) throw new Error(`Generation failed: ${res.statusText}`);

      const data = await res.json();
      console.log("Full Data from API:", data);

      let grid, mappings;
      let nestleFlags = {};

      if (state.flowType === 'nestle') {
        grid = data.grid;
        mappings = {};
        nestleFlags = data.flags || {};
      } else {
        grid = data.mappings.grid;
        mappings = data.mappings.mappings;
      }

      console.log("Grid received:", grid ? grid.length : 0, "rows");
      if (nestleFlags && Object.keys(nestleFlags).length > 0) {
        console.log("Nestle flags:", Object.keys(nestleFlags).length, "flagged rows");
      }

      if (!grid || grid.length === 0) {
        throw new Error("No grid data returned. Please check input files.");
      }
      setState(prev => ({ ...prev, grid, mappings, nestleFlags, step: 'review' }));
    } catch (err: any) {
      console.error("Generation failed", err);
      setError(err.message || "Failed to generate mappings.");
      setState(prev => ({ ...prev, step: 'upload' }));
    }
  };

  const handleCellUpdate = async (rowIdx: number, colIdx: number, value: string) => {
    if (!state.sessionId || !state.grid) return;

    // Optimistic Update
    const newGrid = [...state.grid];
    newGrid[rowIdx] = [...newGrid[rowIdx]];
    newGrid[rowIdx][colIdx] = value;
    setState(prev => ({ ...prev, grid: newGrid }));

    try {
      await fetch(`${API_BASE}/api/mappings/${state.sessionId}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_idx: rowIdx, col_idx: colIdx, value })
      });
    } catch (err) {
      console.error("Cell update failed", err);
    }
  };

  const fetchMapping = async () => {
    if (!state.sessionId) return;
    try {
      // Add timestamp to prevent browser caching
      const res = await fetch(`${API_BASE}/api/mappings/${state.sessionId}?t=${Date.now()}`);
      if (!res.ok) throw new Error("Failed to refresh mapping");
      const data = await res.json();

      setState(prev => ({
        ...prev,
        grid: data.grid,
        mappings: data.mappings
      }));
    } catch (err) {
      console.error("Refresh failed", err);
    }
  };

  const handleDownload = async () => {
    if (!state.sessionId) return;
    window.open(`${API_BASE}/api/download/${state.sessionId}`, '_blank');
  };

  const getColumnLabel = (index: number) => {
    let label = '';
    while (index >= 0) {
      label = String.fromCharCode((index % 26) + 65) + label;
      index = Math.floor(index / 26) - 1;
    }
    return label;
  };

  // Warning Map (only for 850 for now)
  const warningMap = useMemo(() => {
    const map = new Map<number, string>();
    if (state.flowType !== '850' || !state.mappings || !state.grid) return map;

    // Flatten mappings for quick lookup
    const fieldWarnings = new Map<string, string>();
    Object.values(state.mappings as MappingData).forEach(group => {
      Object.entries(group).forEach(([fieldName, data]) => {
        if (data.validation_warning) {
          fieldWarnings.set(fieldName, data.validation_warning);
        }
      });
    });

    // Iterate grid to find row indices
    state.grid.forEach((row, idx) => {
      const fieldName = row[0]; // assuming col 0 is field name
      if (fieldName && typeof fieldName === 'string') {
        if (fieldWarnings.has(fieldName)) {
          map.set(idx, fieldWarnings.get(fieldName)!);
        }
      }
    });
    return map;
  }, [state.mappings, state.grid, state.flowType]);

  /* New State for viewing full cell content */
  const [viewingCell, setViewingCell] = useState<{ content: string; title: string } | null>(null);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0f172a] flex flex-col font-sans text-slate-900 dark:text-slate-100 selection:bg-blue-500/30 selection:text-blue-900 dark:selection:text-white overflow-hidden transition-colors duration-300">

      {/* Copilot Panel */}
      {state.sessionId && (
        <CopilotPanel
          isOpen={!!state.isCopilotOpen}
          onClose={() => setState(prev => ({ ...prev, isCopilotOpen: false }))}
          sessionId={state.sessionId}
          onActionComplete={fetchMapping}
        />
      )}

      {/* Content Modal */}
      <AnimatePresence>
        {viewingCell && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center px-4">
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setViewingCell(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-2xl bg-white dark:bg-[#1e293b] border border-slate-200 dark:border-white/10 rounded-2xl shadow-2xl overflow-hidden"
            >
              <div className="px-6 py-4 border-b border-slate-200 dark:border-white/10 flex items-center justify-between bg-slate-50 dark:bg-white/5">
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">{viewingCell.title}</h3>
                <button onClick={() => setViewingCell(null)} className="p-2 hover:bg-slate-100 dark:hover:bg-white/10 rounded-lg transition-colors">
                  <div className="w-5 h-5 flex flex-col justify-center gap-1.5 rotate-45">
                    <div className="w-full h-0.5 bg-slate-400"></div>
                    <div className="w-full h-0.5 bg-slate-400 -mt-2 rotate-90"></div>
                  </div>
                </button>
              </div>
              <div className="p-6 max-h-[70vh] overflow-y-auto custom-scrollbar">
                <div className="whitespace-pre-wrap font-mono text-sm text-slate-800 dark:text-slate-300 leading-relaxed">
                  {viewingCell.content}
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Header */}
      <header className="bg-white/80 dark:bg-[#1e293b]/50 backdrop-blur-md border-b border-slate-200 dark:border-white/5 px-8 py-4 flex items-center justify-between z-50">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl flex items-center justify-center text-white font-bold text-xl shadow-lg ring-1 ring-white/10">
            <Network className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white leading-none">EDI <span className="text-blue-600 dark:text-cyan-400">NEXUS</span></h1>
            <p className="text-[10px] text-slate-600 dark:text-slate-400 font-bold tracking-[0.2em] uppercase mt-1">Intelligent Mapping Hub</p>
          </div>
        </div>

        <div className="flex items-center gap-4">

          {/* Copilot Toggle */}
          {state.step === 'review' && (
            <button
              onClick={() => setState(prev => ({ ...prev, isCopilotOpen: !prev.isCopilotOpen }))}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-bold transition-all shadow-lg hover:shadow-xl hover:scale-105 active:scale-95
                ${state.isCopilotOpen
                  ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 border border-transparent'
                  : 'bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-violet-500/30'
                }`}
            >
              <Bot className={`w-5 h-5 ${state.isCopilotOpen ? 'animate-none' : 'animate-bounce'}`} />
              {state.isCopilotOpen ? 'Hide Copilot' : 'Open Copilot'}
            </button>
          )}

          <ThemeToggle />
          {state.step !== 'landing' && (
            <button
              onClick={reset}
              className="text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white flex items-center gap-1.5 transition-colors px-3 py-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-white/5"
            >
              <ChevronLeft className="w-4 h-4" /> Start New
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex flex-col relative overflow-hidden">
        <AnimatePresence mode="wait">
          {error && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="absolute top-4 left-1/2 -translate-x-1/2 z-[100] w-full max-w-xl px-4"
            >
              <div className="p-4 bg-red-500/20 border border-red-500/40 rounded-2xl text-red-200 flex items-center gap-3 backdrop-blur-xl shadow-2xl">
                <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
                <span className="text-sm font-medium">{error}</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* LANDING */}
        {state.step === 'landing' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="flex-1 flex flex-col items-center justify-center p-8 text-center"
          >
            <h2 className="text-4xl font-black text-slate-900 dark:text-white mb-3 tracking-tight">Select Workflow</h2>
            <p className="text-slate-600 dark:text-slate-400 text-lg mb-12">Choose the EDI transaction type to proceed.</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full max-w-4xl">
              <button onClick={() => startFlow('850')} className="group relative p-8 bg-white dark:bg-[#1e293b]/50 border border-slate-200 dark:border-white/10 rounded-3xl hover:border-blue-500/50 hover:bg-blue-50 dark:hover:bg-blue-600/5 transition-all text-left shadow-lg dark:shadow-none">
                <div className="w-14 h-14 bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <FileSpreadsheet className="w-8 h-8" />
                </div>
                <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">EDI 850 Flow</h3>
                <p className="text-slate-600 dark:text-slate-400 text-sm">Purchase Order Inbound. Maps 850 data to Oracle interface tables using Sample EDI & Spec.</p>
              </button>

              <button onClick={() => startFlow('856')} className="group relative p-8 bg-white dark:bg-[#1e293b]/50 border border-slate-200 dark:border-white/10 rounded-3xl hover:border-cyan-500/50 hover:bg-cyan-50 dark:hover:bg-cyan-600/5 transition-all text-left shadow-lg dark:shadow-none">
                <div className="w-14 h-14 bg-cyan-100 dark:bg-cyan-500/20 text-cyan-600 dark:text-cyan-400 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <Package className="w-8 h-8" />
                </div>
                <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">EDI 856 Flow</h3>
                <p className="text-slate-600 dark:text-slate-400 text-sm">Advance Ship Notice Outbound. Maps Vendor Spec requirements to outbound definitions.</p>
              </button>

              <button onClick={() => startFlow('nestle')} className="group relative p-8 bg-white dark:bg-[#1e293b]/50 border border-slate-200 dark:border-white/10 rounded-3xl hover:border-emerald-500/50 hover:bg-emerald-50 dark:hover:bg-emerald-600/5 transition-all text-left shadow-lg dark:shadow-none md:col-span-2">
                <div className="w-14 h-14 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <FileText className="w-8 h-8" />
                </div>
                <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Nestle 850 Flow</h3>
                <p className="text-slate-600 dark:text-slate-400 text-sm">Validates Vendor Spec against Nestle/SAP Standard Mapping.</p>
              </button>
            </div>
          </motion.div>
        )}

        {state.step === 'upload' && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="flex-1 flex flex-col items-center justify-center p-8"
          >
            <div className="text-center mb-10">
              <h2 className="text-3xl font-black text-slate-900 dark:text-white mb-3 tracking-tight">
                {state.flowType === '856' ? '856 ASN Workflow' :
                  state.flowType === 'nestle' ? 'Nestle 850 Workflow' : '850 PO Workflow'}
              </h2>
              <p className="text-slate-600 dark:text-slate-400 text-lg">Upload required documents.</p>
            </div>

            {/* PDF INPUT: For Both */}
            <div className="col-span-1 md:col-span-2 max-w-md mx-auto w-full group relative">
              <div className={`absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-blue-500 rounded-3xl blur opacity-20 group-hover:opacity-40 transition duration-500 ${files.pdf ? 'opacity-100' : ''}`}></div>
              <div className={`relative flex flex-col items-center gap-6 p-10 rounded-3xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-[#1e293b]/80 backdrop-blur-xl transition-all cursor-pointer hover:border-blue-500/50 ${files.pdf ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/5' : ''} shadow-xl dark:shadow-none`}>
                <input type="file" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" accept=".pdf" onChange={e => setFiles(prev => ({ ...prev, pdf: e.target.files?.[0] || null }))} />
                <div className={`w-20 h-20 rounded-2xl flex items-center justify-center transition-all duration-500 ${files.pdf ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/30' : 'bg-slate-100 dark:bg-slate-800 text-slate-400 group-hover:scale-110'}`}>
                  {files.pdf ? <CheckCircle className="w-10 h-10" /> : <FileText className="w-10 h-10" />}
                </div>
                <div className="text-center">
                  <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-1">Vendor Spec PDF</h3>
                  <p className="text-xs text-slate-700 font-mono truncate max-w-[200px]">{files.pdf ? files.pdf.name : "Drop .pdf file here"}</p>
                </div>
              </div>
            </div>


            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleFileUpload}
              disabled={!files.pdf}
              className="mt-12 w-full max-w-sm py-5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-2xl font-bold shadow-2xl shadow-blue-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-3 text-lg ring-1 ring-white/10"
            >
              <Play className="w-5 h-5 fill-current" />
              Generate Mapping
            </motion.button>
          </motion.div>
        )}

        {state.step === 'processing' && (
          <div className="flex-1 flex flex-col items-center justify-center">
            {/* Same spinner logic */}
            <div className="relative w-40 h-40 mb-10">
              <div className="absolute inset-0 border-4 border-slate-200 dark:border-slate-800 rounded-full"></div>
              <div className="absolute inset-0 border-t-4 border-blue-500 rounded-full animate-spin"></div>
              <div className="absolute inset-4 border-t-4 border-indigo-400 rounded-full animate-spin-reverse opacity-50"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <FileText className="w-12 h-12 text-blue-500 animate-pulse" />
              </div>
            </div>

            <h2 className="text-3xl font-black text-slate-900 dark:text-white mb-3">Creating Mappings</h2>
            <div className="flex items-center gap-2">
              <p className="text-slate-500 dark:text-slate-400 font-medium lowercase tracking-wider">Analyzing PDF & Generating Rules...</p>
            </div>
          </div>
        )}

        {state.step === 'review' && state.grid && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex-1 flex flex-col h-full bg-slate-50 dark:bg-[#0f172a]"
          >
            {/* Spreadsheet Toolbar */}
            <div className="px-6 py-3 bg-white/50 dark:bg-[#1e293b]/50 border-b border-slate-200 dark:border-white/5 flex items-center justify-between backdrop-blur-md">
              <div className="flex items-center gap-6">
                <div className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase tracking-widest border-r border-slate-300 dark:border-white/10 pr-6">
                  {state.flowType === '856' ? '856 Editor' :
                    state.flowType === 'nestle' ? 'Nestle Gap Analysis' : '850 Editor'}
                </div>
                <div className="flex items-center gap-2 text-[11px] text-slate-700 dark:text-slate-400 font-medium">
                  <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                  Connected to Mapping Engine
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => window.alert("Work in Progress: OpenText Consultant Integration is currently under development.")}
                  className="px-6 py-2 bg-blue-600/20 text-blue-600 dark:text-blue-400 hover:bg-blue-600 hover:text-white border border-blue-600/30 rounded-lg text-xs font-bold transition-all flex items-center gap-2"
                >
                  <Send className="w-4 h-4" /> Send to OpenText
                </button>
                <button
                  onClick={handleDownload}
                  className="px-6 py-2 bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600 hover:text-white border border-emerald-600/30 rounded-lg text-xs font-bold transition-all flex items-center gap-2"
                >
                  <Download className="w-4 h-4" /> Download .xlsx
                </button>
              </div>
            </div>

            {/* Grid Container */}
            <div className="flex-1 overflow-auto custom-scrollbar bg-slate-50 dark:bg-[#0f172a] p-4">
              <div className="inline-block min-w-full align-middle">
                <table className="border-collapse text-[13px] min-w-full divide-y divide-slate-200 dark:divide-white/10 border border-slate-200 dark:border-white/10">
                  <thead className="bg-slate-100 dark:bg-[#1e293b] sticky top-0 z-20">
                    <tr>
                      <th className="w-12 border border-slate-200 dark:border-white/10 p-2 text-[10px] text-slate-700 text-center font-bold">#</th>
                      {state.grid[0].map((header: string, i: number) => {
                        // Widen certain columns based on flow
                        // Nestle 16-col: SAP Seg Desc(1), SAP Field Desc(3), X12 Elem Desc(8), Mapping Rule(9), Notes(15)
                        const isWide = i === 9 || (state.flowType === '856' && i === 6) ||
                          (state.flowType === 'nestle' && [1, 3, 8, 9, 15].includes(i));
                        return (
                          <th key={i} className={`${isWide ? 'min-w-[300px]' : 'min-w-[150px]'} border border-slate-200 dark:border-white/10 p-3 text-xs text-slate-900 dark:text-slate-300 font-bold text-left uppercase tracking-tight`}>
                            <div className="flex flex-col gap-1">
                              <span className="text-[10px] text-blue-600 dark:text-blue-400 font-mono">{getColumnLabel(i)}</span>
                              <span>{header}</span>
                            </div>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-[#0f172a] divide-y divide-slate-100 dark:divide-white/5">
                    {state.grid.slice(1).map((row, dataIdx) => {
                      const rIdx = dataIdx + 1; // logical row index including header
                      const cellWarning = warningMap.get(rIdx);

                      const isNestle = state.flowType === 'nestle';
                      const mappingSource = isNestle ? row[13] : ''; // Mapping Source at index 13
                      let rowClass = '';
                      if (isNestle) {
                        if (mappingSource === 'STANDARD+PDF') rowClass = 'bg-emerald-50 dark:bg-emerald-900/30 border-l-4 border-l-emerald-500';
                        else if (mappingSource === 'STANDARD') rowClass = 'bg-blue-50 dark:bg-blue-900/30 border-l-4 border-l-blue-500';
                        else if (mappingSource === 'AI_MATCH') rowClass = 'bg-amber-50 dark:bg-amber-900/30 border-l-4 border-l-amber-500';
                        else if (mappingSource === 'UNMAPPED') rowClass = 'bg-slate-50 dark:bg-slate-800/50 border-l-4 border-l-slate-400';
                      }

                      return (
                        <tr key={rIdx} className={`hover:bg-slate-50 dark:hover:bg-white/[0.03] group transition-colors ${rowClass}`}>
                          <td className="bg-slate-50 dark:bg-[#1e293b]/50 border border-slate-200 dark:border-white/10 text-center text-[10px] text-slate-700 font-bold py-2 px-1">
                            {rIdx}
                          </td>
                          {row.map((cell, cIdx) => {
                            // Editable Logic
                            let isEditable = false;
                            if (state.flowType === '850') {
                              isEditable = (cIdx === 1 || cIdx === 2);
                            } else if (state.flowType === '856') {
                              isEditable = [3, 4, 5, 6].includes(cIdx);
                            } else if (state.flowType === 'nestle') {
                              isEditable = false;
                            }

                            // Interactive Columns for Modal View:
                            // Nestle 16-col: SAP Field Desc(3), X12 Elem Desc(8), Mapping Rule(9), Notes(15)
                            const isInteractive = (cIdx === 9 ||
                              (state.flowType === '856' && cIdx === 6) ||
                              (state.flowType === 'nestle' && [3, 8, 9, 15].includes(cIdx)));

                            return (
                              <td
                                key={cIdx}
                                title={
                                  // Show flag reason as tooltip for flagged Mapping Rule cells
                                  (isNestle && state.nestleFlags?.[rIdx]?.col === cIdx)
                                    ? `⚠ ${state.nestleFlags[rIdx].reason}`
                                    : cellWarning || undefined
                                }
                                className={`border border-slate-200 dark:border-white/10 p-0 relative group/cell
                                  ${(cellWarning && isEditable) ? 'bg-red-500/25 border-red-500/50' : ''}
                                  ${(isNestle && state.nestleFlags?.[rIdx]?.col === cIdx) ? 'bg-orange-200 dark:bg-orange-500/30 border-orange-400 dark:border-orange-500/50 ring-1 ring-orange-400/50' : ''}
                                `}
                              >
                                <input
                                  key={cell}
                                  type="text"
                                  defaultValue={cell || ""}
                                  readOnly={!isEditable}
                                  onClick={() => {
                                    if (isInteractive) {
                                      setViewingCell({
                                        title: state.grid![0][cIdx],
                                        content: cell
                                      });
                                    }
                                    // Also allow clicking flagged cell to see full reason
                                    if (isNestle && state.nestleFlags?.[rIdx]?.col === cIdx) {
                                      setViewingCell({
                                        title: `⚠ Flag: ${state.grid![0][cIdx]}`,
                                        content: `Mapping Rule:\n${cell}\n\nFlag Reason:\n${state.nestleFlags[rIdx].reason}`
                                      });
                                    }
                                  }}
                                  onBlur={(e) => {
                                    if (e.target.value !== cell) {
                                      handleCellUpdate(rIdx, cIdx, e.target.value);
                                    }
                                  }}
                                  className={`w-full min-h-[40px] px-3 py-2 outline-none bg-transparent transition-all
                                    ${isInteractive ? 'cursor-pointer hover:bg-black/5 dark:hover:bg-white/5' : ''}
                                    ${(isNestle && state.nestleFlags?.[rIdx]?.col === cIdx) ? 'cursor-pointer text-orange-800 dark:text-orange-200 font-medium' : ''}
                                    ${isEditable ? 'text-black font-medium dark:text-blue-50 focus:bg-blue-50 dark:focus:bg-blue-500/10 focus:ring-1 focus:ring-blue-500/30' :
                                      'text-slate-600'
                                    }`}
                                />
                              </td>
                            );
                          })}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-2 bg-slate-100 dark:bg-[#1e293b]/30 border-t border-slate-200 dark:border-white/5 flex items-center justify-between text-[10px] text-slate-500 font-medium">
              <div className="flex gap-4">
                <span>Rows: <span className="text-slate-700 dark:text-slate-300">{state.grid ? state.grid.length - 1 : 0}</span></span>
              </div>
              {state.flowType === 'nestle' && (
                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500"></span> Standard+PDF</span>
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-blue-500"></span> Standard Only</span>
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-amber-500"></span> AI Match</span>
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-slate-400"></span> Unmapped</span>
                </div>
              )}
              <div className="flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></div>
                Ready for Export
              </div>
            </div>
          </motion.div>
        )}
      </main>
    </div >
  );
}

export default App;
