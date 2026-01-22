import React, { useState, useRef, useCallback } from "react";
import TreeVisualization from "./components/TreeVisualization";
import CodePanel from "./components/CodePanel";

const API_BASE = "http://localhost:3000";

function App() {
  // Project state - stores ALL data from backend
  const [projectData, setProjectData] = useState(null);
  const [projectName, setProjectName] = useState("");
  
  // View state
  const [selectedFile, setSelectedFile] = useState(null);
  const [highlightLine, setHighlightLine] = useState(null);
  const [showCodePanel, setShowCodePanel] = useState(false);
  
  // Single file / Code mode
  const [mode, setMode] = useState("empty"); // 'empty', 'project', 'single', 'code'
  const [singleFileData, setSingleFileData] = useState(null);
  const [codeInput, setCodeInput] = useState(`function greet(name) {
  console.log("Hello, " + name);
  return name.toUpperCase();
}

const result = greet("World");`);
  const [errorLine, setErrorLine] = useState(null);
  
  // Loading/Error state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // File inputs
  const zipInputRef = useRef(null);
  const fileInputRef = useRef(null);

  // ========================================
  // UPLOAD HANDLERS
  // ========================================

  const handleZipUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch(`${API_BASE}/upload/zip`, {
        method: 'POST',
        body: formData
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to upload ZIP");
      }
      
      const data = await res.json();
      console.log("Project loaded:", data.summary);
      
      setProjectData(data);
      setProjectName(data.projectName || file.name.replace('.zip', ''));
      setMode("project");
      
      // Select first file
      const fileNames = Object.keys(data.files);
      if (fileNames.length > 0) {
        setSelectedFile(fileNames[0]);
      }
      
      setSingleFileData(null);
      
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      if (zipInputRef.current) zipInputRef.current.value = '';
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch(`${API_BASE}/upload/file`, {
        method: 'POST',
        body: formData
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to upload file");
      }
      
      const data = await res.json();
      console.log("File parsed:", data.filename);
      
      setSingleFileData(data);
      setMode("single");
      setProjectData(null);
      setSelectedFile(data.filename);
      
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleParseCode = async () => {
    if (!codeInput.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch(`${API_BASE}/parse/code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: codeInput,
          errorLine: errorLine || undefined,
          filename: "snippet.js"
        })
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to parse code");
      }
      
      const data = await res.json();
      console.log("Code parsed");
      
      setSingleFileData(data);
      setMode("code");
      setProjectData(null);
      setSelectedFile("snippet.js");
      
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // ========================================
  // NAVIGATION HANDLERS
  // ========================================

  // Handle clicking a tree node - show code panel at that line
  const handleNodeClick = useCallback((node) => {
    if (node.loc?.start?.line) {
      setHighlightLine(node.loc.start.line);
      setShowCodePanel(true);
    }
  }, []);

  // Handle clicking a reference node - navigate to target file
  const handleReferenceClick = useCallback((node) => {
    if (node.targetFile && projectData?.files?.[node.targetFile]) {
      setSelectedFile(node.targetFile);
      setHighlightLine(node.targetLine || 1);
      setShowCodePanel(true);
    }
  }, [projectData]);

  // Get current visualization data
  const getCurrentTree = () => {
    if (mode === "project" && projectData && selectedFile) {
      return projectData.files[selectedFile]?.tree;
    }
    return singleFileData?.tree;
  };

  const getCurrentContent = () => {
    if (mode === "project" && projectData && selectedFile) {
      return projectData.files[selectedFile]?.content;
    }
    return singleFileData?.content;
  };

  const currentTree = getCurrentTree();
  const currentContent = getCurrentContent();

  // ========================================
  // RENDER
  // ========================================

  return (
    <div className="h-screen flex flex-col bg-slate-900 text-white overflow-hidden">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-4 py-3 flex items-center gap-4 shrink-0">
        <h1 className="text-xl font-bold text-blue-400 flex items-center gap-2">
          🌳 AST Visualizer
        </h1>
        
        {projectName && (
          <span className="text-slate-400 text-sm">
            {projectName} • {Object.keys(projectData?.files || {}).length} files
          </span>
        )}
        
        <div className="flex-1" />
        
        {/* Upload buttons */}
        <label className="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded-lg text-sm font-medium cursor-pointer transition-colors">
          📦 Upload Project (ZIP)
          <input
            ref={zipInputRef}
            type="file"
            accept=".zip"
            onChange={handleZipUpload}
            className="hidden"
          />
        </label>
        
        <label className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm font-medium cursor-pointer transition-colors">
          📄 Upload File
          <input
            ref={fileInputRef}
            type="file"
            accept=".js,.jsx,.ts,.tsx,.mjs,.cjs"
            onChange={handleFileUpload}
            className="hidden"
          />
        </label>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-red-900/70 border-b border-red-700 px-4 py-2 text-red-200 text-sm flex items-center gap-2 shrink-0">
          <span>⚠️ {error}</span>
          <button onClick={() => setError(null)} className="ml-auto hover:text-white">✕</button>
        </div>
      )}

      {/* Main layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar - Files or Code input */}
        <aside className="w-72 bg-slate-800 border-r border-slate-700 flex flex-col shrink-0">
          {/* Tabs */}
          <div className="flex border-b border-slate-700">
            <button
              onClick={() => mode === "code" ? setMode(projectData ? "project" : "empty") : null}
              className={`flex-1 px-4 py-2 text-sm font-medium ${mode !== "code" ? "bg-slate-700 text-blue-400" : "text-slate-400 hover:text-white"}`}
            >
              📂 Files
            </button>
            <button
              onClick={() => setMode("code")}
              className={`flex-1 px-4 py-2 text-sm font-medium ${mode === "code" ? "bg-slate-700 text-blue-400" : "text-slate-400 hover:text-white"}`}
            >
              ✏️ Code
            </button>
          </div>

          {mode === "code" ? (
            /* Code input panel */
            <div className="flex-1 flex flex-col p-3 gap-3 overflow-hidden">
              <textarea
                className="flex-1 bg-slate-900 font-mono text-green-300 p-3 rounded-lg border border-slate-600 text-sm resize-none"
                value={codeInput}
                onChange={(e) => setCodeInput(e.target.value)}
                placeholder="Enter JavaScript/TypeScript code..."
                spellCheck={false}
              />
              <div className="flex gap-2 items-center">
                <input
                  type="number"
                  className="w-20 bg-slate-900 text-white px-2 py-1.5 rounded border border-slate-600 text-sm"
                  placeholder="Err line"
                  value={errorLine || ''}
                  onChange={(e) => setErrorLine(e.target.value ? parseInt(e.target.value) : null)}
                  min={1}
                />
                <button
                  onClick={handleParseCode}
                  className="flex-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium disabled:opacity-50"
                  disabled={loading || !codeInput.trim()}
                >
                  {loading ? "..." : "Visualize"}
                </button>
              </div>
            </div>
          ) : (
            /* File list */
            <div className="flex-1 overflow-auto p-2">
              {mode === "project" && projectData ? (
                <div className="space-y-1">
                  {Object.values(projectData.files).map((file) => (
                    <FileItem
                      key={file.name}
                      file={file}
                      isSelected={selectedFile === file.name}
                      onClick={() => {
                        setSelectedFile(file.name);
                        setHighlightLine(null);
                      }}
                    />
                  ))}
                </div>
              ) : mode === "single" && singleFileData ? (
                <div className="space-y-1">
                  <FileItem
                    file={{ name: singleFileData.filename, error: singleFileData.error }}
                    isSelected={true}
                    onClick={() => {}}
                  />
                </div>
              ) : (
                <div className="text-slate-500 text-sm p-4 text-center">
                  <div className="text-4xl mb-3">📁</div>
                  <p>Upload a ZIP project or single file to visualize its AST</p>
                </div>
              )}
            </div>
          )}

          {/* References panel for project mode */}
          {mode === "project" && selectedFile && projectData?.files?.[selectedFile] && (
            <ReferencesPanel
              file={projectData.files[selectedFile]}
              onReferenceClick={(targetFile, targetLine) => {
                setSelectedFile(targetFile);
                setHighlightLine(targetLine);
                setShowCodePanel(true);
              }}
            />
          )}
        </aside>

        {/* Main content area */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Toolbar */}
          <div className="bg-slate-800 border-b border-slate-700 px-4 py-2 flex items-center gap-4 shrink-0">
            {selectedFile && (
              <span className="text-sm font-mono text-slate-300">📄 {selectedFile}</span>
            )}
            
            <div className="flex-1" />
            
            {currentContent && (
              <button
                onClick={() => setShowCodePanel(!showCodePanel)}
                className={`px-3 py-1 rounded text-xs font-medium ${showCodePanel ? 'bg-blue-600' : 'bg-slate-700 hover:bg-slate-600'}`}
              >
                {showCodePanel ? '✕ Hide Code' : '📝 Show Code'}
              </button>
            )}
            
            {/* Legend */}
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-slate-600"></span> Node
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-red-600"></span> Error
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-cyan-600"></span> Reference
              </span>
            </div>
          </div>

          {/* Content */}
          {loading ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="animate-spin w-10 h-10 border-3 border-blue-400 border-t-transparent rounded-full mx-auto mb-3"></div>
                <p className="text-slate-400">Processing...</p>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex overflow-hidden">
              {/* Tree visualization */}
              <div className={`flex-1 overflow-auto ${showCodePanel ? 'w-1/2' : 'w-full'}`}>
                {currentTree ? (
                  <TreeVisualization
                    tree={currentTree}
                    onNodeClick={handleNodeClick}
                    onReferenceClick={handleReferenceClick}
                  />
                ) : (
                  <div className="h-full flex items-center justify-center text-slate-500">
                    <div className="text-center">
                      <div className="text-6xl mb-4">🌳</div>
                      <p className="text-lg">No AST to display</p>
                      <p className="text-sm mt-2">Upload a file or enter code to visualize</p>
                    </div>
                  </div>
                )}
              </div>

              {/* Code panel */}
              {showCodePanel && currentContent && (
                <div className="w-1/2 border-l border-slate-700">
                  <CodePanel
                    content={currentContent}
                    highlightLine={highlightLine}
                    filename={selectedFile}
                  />
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

// ========================================
// SUB-COMPONENTS
// ========================================

function FileItem({ file, isSelected, onClick }) {
  const hasError = !!file.error;
  const refCount = (file.outgoingRefs?.length || 0) + (file.incomingRefs?.length || 0);
  
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 rounded text-sm transition-colors flex items-center gap-2 ${
        isSelected
          ? 'bg-blue-600/30 text-blue-300 border border-blue-500/50'
          : hasError
            ? 'bg-red-900/30 text-red-300 hover:bg-red-900/50'
            : 'text-slate-300 hover:bg-slate-700'
      }`}
    >
      <span className="flex-1 font-mono truncate">
        {hasError ? '⚠️' : '📄'} {file.name}
      </span>
      {refCount > 0 && (
        <span className="px-1.5 py-0.5 bg-slate-700 rounded text-xs text-slate-400">
          {refCount}
        </span>
      )}
    </button>
  );
}

function ReferencesPanel({ file, onReferenceClick }) {
  const outgoing = file.outgoingRefs || [];
  const incoming = file.incomingRefs || [];
  
  if (outgoing.length === 0 && incoming.length === 0) return null;
  
  return (
    <div className="border-t border-slate-700 p-3 max-h-48 overflow-auto shrink-0">
      <h3 className="text-xs font-semibold text-slate-400 mb-2">
        🔗 References ({outgoing.length + incoming.length})
      </h3>
      <div className="space-y-1">
        {outgoing.map((ref, i) => (
          <button
            key={`out-${i}`}
            onClick={() => onReferenceClick(ref.toFile, ref.toLine)}
            className="w-full text-left px-2 py-1 bg-cyan-900/30 hover:bg-cyan-900/50 rounded text-xs text-cyan-300"
          >
            → {ref.toFile} <span className="text-slate-500">({ref.toName})</span>
          </button>
        ))}
        {incoming.map((ref, i) => (
          <button
            key={`in-${i}`}
            onClick={() => onReferenceClick(ref.fromFile, ref.fromLine)}
            className="w-full text-left px-2 py-1 bg-amber-900/30 hover:bg-amber-900/50 rounded text-xs text-amber-300"
          >
            ← {ref.fromFile} <span className="text-slate-500">({ref.fromName})</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default App;
