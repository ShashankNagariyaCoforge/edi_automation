import React, { useState, useMemo, useCallback } from 'react';
import { Upload, FileText, CheckCircle, Download, Play, AlertCircle, ChevronLeft, Network, Package, FileSpreadsheet } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

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
  flowType: '850' | '856' | null;
  sessionId: string | null;
  grid: any[][] | null;
  mappings: MappingData | any | null; // Flexible for 856
}

function App() {
  const [state, setState] = useState<AppState>({
    step: 'landing',
    flowType: null,
    sessionId: null,
    grid: null,
    mappings: null,
  });

  const [files, setFiles] = useState<{ edi: File | null; pdf: File | null }>({
    edi: null,
    pdf: null,
  });

  const [error, setError] = useState<string | null>(null);

  // Reset helper
  const reset = () => {
    setState({
      step: 'landing',
      flowType: null,
      sessionId: null,
      grid: null,
      mappings: null,
    });
    setFiles({ edi: null, pdf: null });
    setError(null);
  };

  const startFlow = (type: '850' | '856') => {
    setState(p => ({ ...p, flowType: type, step: 'upload' }));
    setFiles({ edi: null, pdf: null }); // Clear files on switch
  };

  const handleFileUpload = async () => {
    if (!state.flowType) return;

    // Validation
    if (state.flowType === '850' && (!files.edi || !files.pdf)) return;
    if (state.flowType === '856' && !files.pdf) return;

    setError(null);
    setState(prev => ({ ...prev, step: 'processing' }));

    const formData = new FormData();
    if (files.edi) formData.append('edi_file', files.edi);
    if (files.pdf) formData.append('pdf_file', files.pdf);

    try {
      const endpoint = state.flowType === '856'
        ? 'http://localhost:8001/api/856/upload'
        : 'http://localhost:8001/api/upload';

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
      const endpoint = state.flowType === '856'
        ? `http://localhost:8001/api/856/generate/${sessionId}`
        : `http://localhost:8001/api/generate/${sessionId}`;

      const res = await fetch(endpoint, { method: 'POST' });
      if (!res.ok) throw new Error(`Generation failed: ${res.statusText}`);

      const data = await res.json();
      console.log("Full Data from API:", data);

      const { grid, mappings } = data.mappings;
      console.log("Grid received:", grid ? grid.length : 0, "rows");

      if (!grid || grid.length === 0) {
        throw new Error("No grid data returned. Please check input files.");
      }
      setState(prev => ({ ...prev, grid, mappings, step: 'review' }));
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
      await fetch(`http://localhost:8001/api/mappings/${state.sessionId}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ row_idx: rowIdx, col_idx: colIdx, value })
      });
    } catch (err) {
      console.error("Cell update failed", err);
    }
  };

  const handleDownload = async () => {
    if (!state.sessionId) return;
    window.open(`http://localhost:8001/api/download/${state.sessionId}`, '_blank');
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
    <div className="min-h-screen bg-[#0f172a] flex flex-col font-sans text-slate-100 selection:bg-blue-500/30 selection:text-white overflow-hidden">
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
              className="relative w-full max-w-2xl bg-[#1e293b] border border-white/10 rounded-2xl shadow-2xl overflow-hidden"
            >
              <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between bg-white/5">
                <h3 className="text-lg font-bold text-white">{viewingCell.title}</h3>
                <button onClick={() => setViewingCell(null)} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
                  <div className="w-5 h-5 flex flex-col justify-center gap-1.5 rotate-45">
                    <div className="w-full h-0.5 bg-slate-400"></div>
                    <div className="w-full h-0.5 bg-slate-400 -mt-2 rotate-90"></div>
                  </div>
                </button>
              </div>
              <div className="p-6 max-h-[70vh] overflow-y-auto custom-scrollbar">
                <div className="whitespace-pre-wrap font-mono text-sm text-slate-300 leading-relaxed">
                  {viewingCell.content}
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Header */}
      <header className="bg-[#1e293b]/50 backdrop-blur-md border-b border-white/5 px-8 py-4 flex items-center justify-between z-50">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-xl flex items-center justify-center text-white font-bold text-xl shadow-lg ring-1 ring-white/10">
            <Network className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white leading-none">EDI <span className="text-cyan-400">NEXUS</span></h1>
            <p className="text-[10px] text-slate-400 font-bold tracking-[0.2em] uppercase mt-1">Intelligent Mapping Hub</p>
          </div>
        </div>

        {state.step !== 'landing' && (
          <button
            onClick={reset}
            className="text-xs font-medium text-slate-400 hover:text-white flex items-center gap-1.5 transition-colors px-3 py-1.5 rounded-lg hover:bg-white/5"
          >
            <ChevronLeft className="w-4 h-4" /> Start New
          </button>
        )}
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
            <h2 className="text-4xl font-black text-white mb-3 tracking-tight">Select Workflow</h2>
            <p className="text-slate-400 text-lg mb-12">Choose the EDI transaction type to proceed.</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 w-full max-w-4xl">
              <button onClick={() => startFlow('850')} className="group relative p-8 bg-[#1e293b]/50 border border-white/10 rounded-3xl hover:border-blue-500/50 hover:bg-blue-600/5 transition-all text-left">
                <div className="w-14 h-14 bg-blue-500/20 text-blue-400 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <FileSpreadsheet className="w-8 h-8" />
                </div>
                <h3 className="text-2xl font-bold text-white mb-2">EDI 850 Flow</h3>
                <p className="text-slate-400 text-sm">Purchase Order Inbound. Maps 850 data to Oracle interface tables using Sample EDI & Spec.</p>
              </button>

              <button onClick={() => startFlow('856')} className="group relative p-8 bg-[#1e293b]/50 border border-white/10 rounded-3xl hover:border-cyan-500/50 hover:bg-cyan-600/5 transition-all text-left">
                <div className="w-14 h-14 bg-cyan-500/20 text-cyan-400 rounded-2xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                  <Package className="w-8 h-8" />
                </div>
                <h3 className="text-2xl font-bold text-white mb-2">EDI 856 Flow</h3>
                <p className="text-slate-400 text-sm">Advance Ship Notice Outbound. Maps Vendor Spec requirements to outbound definitions.</p>
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
              <h2 className="text-3xl font-black text-white mb-3 tracking-tight">
                {state.flowType === '856' ? '856 ASN Workflow' : '850 PO Workflow'}
              </h2>
              <p className="text-slate-400 text-lg">Upload required documents.</p>
            </div>

            <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-8 justify-center">
              {/* EDI INPUT: Only for 850 */}
              {state.flowType === '850' && (
                <div className="group relative">
                  <div className={`absolute -inset-0.5 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-3xl blur opacity-20 group-hover:opacity-40 transition duration-500 ${files.edi ? 'opacity-100' : ''}`}></div>
                  <div className={`relative flex flex-col items-center gap-6 p-10 rounded-3xl border border-white/10 bg-[#1e293b]/80 backdrop-blur-xl transition-all cursor-pointer hover:border-blue-500/50 ${files.edi ? 'border-blue-500 bg-blue-500/5' : ''}`}>
                    <input type="file" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" accept=".txt" onChange={e => setFiles(prev => ({ ...prev, edi: e.target.files?.[0] || null }))} />
                    <div className={`w-20 h-20 rounded-2xl flex items-center justify-center transition-all duration-500 ${files.edi ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/30' : 'bg-slate-800 text-slate-400 group-hover:scale-110'}`}>
                      {files.edi ? <CheckCircle className="w-10 h-10" /> : <FileText className="w-10 h-10" />}
                    </div>
                    <div className="text-center">
                      <h3 className="text-xl font-bold text-white mb-1">Sample EDI File</h3>
                      <p className="text-xs text-slate-500 font-mono truncate max-w-[200px]">{files.edi ? files.edi.name : "Drop .txt file here"}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* PDF INPUT: For Both */}
              <div className={`group relative ${state.flowType === '856' ? 'col-span-1 md:col-start-1 md:col-end-3 max-w-md mx-auto w-full' : ''}`}>
                <div className={`absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-blue-500 rounded-3xl blur opacity-20 group-hover:opacity-40 transition duration-500 ${files.pdf ? 'opacity-100' : ''}`}></div>
                <div className={`relative flex flex-col items-center gap-6 p-10 rounded-3xl border border-white/10 bg-[#1e293b]/80 backdrop-blur-xl transition-all cursor-pointer hover:border-blue-500/50 ${files.pdf ? 'border-blue-500 bg-blue-500/5' : ''}`}>
                  <input type="file" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" accept=".pdf" onChange={e => setFiles(prev => ({ ...prev, pdf: e.target.files?.[0] || null }))} />
                  <div className={`w-20 h-20 rounded-2xl flex items-center justify-center transition-all duration-500 ${files.pdf ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/30' : 'bg-slate-800 text-slate-400 group-hover:scale-110'}`}>
                    {files.pdf ? <CheckCircle className="w-10 h-10" /> : <FileText className="w-10 h-10" />}
                  </div>
                  <div className="text-center">
                    <h3 className="text-xl font-bold text-white mb-1">Vendor Spec PDF</h3>
                    <p className="text-xs text-slate-500 font-mono truncate max-w-[200px]">{files.pdf ? files.pdf.name : "Drop .pdf file here"}</p>
                  </div>
                </div>
              </div>
            </div>

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleFileUpload}
              disabled={state.flowType === '850' ? (!files.edi || !files.pdf) : (!files.pdf)}
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
              <div className="absolute inset-0 border-4 border-slate-800 rounded-full"></div>
              <div className="absolute inset-0 border-t-4 border-blue-500 rounded-full animate-spin"></div>
              <div className="absolute inset-4 border-t-4 border-indigo-400 rounded-full animate-spin-reverse opacity-50"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <FileText className="w-12 h-12 text-blue-500 animate-pulse" />
              </div>
            </div>

            <h2 className="text-3xl font-black text-white mb-3">Creating Mappings</h2>
            <div className="flex items-center gap-2">
              <p className="text-slate-400 font-medium lowercase tracking-wider">Analyzing PDF & Generating Rules...</p>
            </div>
          </div>
        )}

        {state.step === 'review' && state.grid && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex-1 flex flex-col h-full bg-[#0f172a]"
          >
            {/* Spreadsheet Toolbar */}
            <div className="px-6 py-3 bg-[#1e293b]/50 border-b border-white/5 flex items-center justify-between backdrop-blur-md">
              <div className="flex items-center gap-6">
                <div className="text-xs font-bold text-blue-400 uppercase tracking-widest border-r border-white/10 pr-6">
                  {state.flowType === '856' ? '856 Editor' : '850 Editor'}
                </div>
                <div className="flex items-center gap-2 text-[11px] text-slate-400 font-medium">
                  <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                  Connected to Mapping Engine
                </div>
              </div>
              <button
                onClick={handleDownload}
                className="px-6 py-2 bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600 hover:text-white border border-emerald-600/30 rounded-lg text-xs font-bold transition-all flex items-center gap-2"
              >
                <Download className="w-4 h-4" /> Download .xlsx
              </button>
            </div>

            {/* Grid Container */}
            <div className="flex-1 overflow-auto custom-scrollbar bg-[#0f172a] p-4">
              <div className="inline-block min-w-full align-middle">
                <table className="border-collapse text-[13px] min-w-full divide-y divide-white/10 border border-white/10">
                  <thead className="bg-[#1e293b] sticky top-0 z-20">
                    <tr>
                      <th className="w-12 border border-white/10 p-2 text-[10px] text-slate-500 text-center font-bold">#</th>
                      {state.grid[0].map((header, i) => (
                        <th key={i} className={`min-w-[150px] border border-white/10 p-3 text-xs text-slate-300 font-bold text-left uppercase tracking-tight`}>
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] text-blue-400 font-mono">{getColumnLabel(i)}</span>
                            <span>{header}</span>
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="bg-[#0f172a] divide-y divide-white/5">
                    {state.grid.slice(1).map((row, dataIdx) => {
                      const rIdx = dataIdx + 1; // logical row index including header
                      const cellWarning = warningMap.get(rIdx);

                      return (
                        <tr key={rIdx} className="hover:bg-white/[0.03] group transition-colors">
                          <td className="bg-[#1e293b]/50 border border-white/10 text-center text-[10px] text-slate-500 font-bold py-2 px-1">
                            {rIdx}
                          </td>
                          {row.map((cell, cIdx) => {
                            const isHeader = false; // we sliced header

                            // Editable Logic
                            let isEditable = false;
                            if (state.flowType === '850') {
                              isEditable = (cIdx === 1 || cIdx === 2);
                            } else if (state.flowType === '856') {
                              // New Columns:
                              // 0: Seg, 1: Occ, 2: Elem, 3: Type, 4: Source, 5: Hardcode, 6: Meaning, 7: Req
                              // Allow editing Type(3), Source(4), Hardcode(5), Meaning(6)
                              isEditable = [3, 4, 5, 6].includes(cIdx);
                            }

                            const isRecordGroup = String(row[0]).includes("Record") || String(row[0]).includes("RECORD");
                            // ^^ might trigger falsely for 856 "Record" field, but 856 col 0 is "ST01" etc.

                            return (
                              <td
                                key={cIdx}
                                title={cellWarning}
                                className={`border border-white/10 p-0 relative group/cell ${(cellWarning && isEditable) ? 'bg-red-500/10 border-red-500/30' : ''}`}
                              >
                                <input
                                  type="text"
                                  defaultValue={cell || ""}
                                  readOnly={!isEditable}
                                  onBlur={(e) => {
                                    if (e.target.value !== cell) {
                                      handleCellUpdate(rIdx, cIdx, e.target.value);
                                    }
                                  }}
                                  className={`w-full min-h-[40px] px-3 py-2 outline-none bg-transparent transition-all ${isEditable ? 'text-blue-50 focus:bg-blue-500/10 focus:ring-1 focus:ring-blue-500/30' :
                                    'text-slate-400'
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
            <div className="px-6 py-2 bg-[#1e293b]/30 border-t border-white/5 flex items-center justify-between text-[10px] text-slate-500 font-medium">
              <div className="flex gap-4">
                <span>Rows: <span className="text-slate-300">{state.grid ? state.grid.length - 1 : 0}</span></span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></div>
                Ready for Export
              </div>
            </div>
          </motion.div>
        )}
      </main>
    </div>
  );
}

export default App;
