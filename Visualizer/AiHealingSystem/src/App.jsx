import React, { useState, useRef, useCallback, useMemo, useEffect } from "react";
import TreeVisualization from "./components/TreeVisualization";
import CodePanel from "./components/CodePanel";
import {
  FirstAidKitIcon,
  TreeStructureIcon,
  FileArrowUpIcon,
  FolderOpenIcon,
  PencilSimpleIcon,
  WarningCircleIcon,
  FileCodeIcon,
  FileJsIcon,
  FileTsIcon,
  FileHtmlIcon,
  FileCssIcon,
  FilePyIcon,
  FileCIcon,
  FileCppIcon,
  FileRsIcon,
  FileIcon,
  CodeBlockIcon,
  UploadIcon,
  EyeIcon,
  EyeSlashIcon,
  CircleIcon,
  LinkIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
  SpinnerGapIcon,
  XIcon,
} from "@phosphor-icons/react";

const API_BASE = ""; // All endpoints proxied to FastAPI backend (port 8000)

/**
 * Build a map of line numbers to tree nodes for code→tree navigation
 */
function buildNodesByLine(tree, prefix = 'root') {
  const map = {};
  
  function walk(node, nodeId) {
    if (!node) return;
    
    if (node.loc?.start?.line) {
      const startLine = node.loc.start.line;
      const endLine = node.loc.end?.line || startLine;
      
      for (let line = startLine; line <= endLine; line++) {
        if (!map[line]) map[line] = [];
        map[line].push({ ...node, nodeId });
      }
    }
    
    if (node.children) {
      node.children.forEach((child, i) => {
        walk(child, `${nodeId}-${i}`);
      });
    }
  }
  
  walk(tree, prefix);
  return map;
}

// No navigation tabs – the React app is a pure AST visualizer.

function App() {
  // Project state - stores ALL data from backend
  const [projectData, setProjectData] = useState(null);
  const [projectName, setProjectName] = useState("");
  
  // View state
  const [selectedFile, setSelectedFile] = useState(null);
  const [highlightLine, setHighlightLine] = useState(null);
  const [showCodePanel, setShowCodePanel] = useState(false);
  const [focusedNodeId, setFocusedNodeId] = useState(null); // For code→tree navigation
  
  // Single file / Code mode
  const [mode, setMode] = useState("empty"); // 'empty', 'project', 'single', 'code'
  const [singleFileData, setSingleFileData] = useState(null);
  const [codeInput, setCodeInput] = useState(`function greet(name) {
  console.log("Hello, " + name);
  return name.toUpperCase();
}

const result = greet("World");`);
  const [errorLine, setErrorLine] = useState(null);
  const [codeLanguage, setCodeLanguage] = useState(".js"); // File extension for language detection
  
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
          filename: `snippet${codeLanguage}`
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
      setFocusedNodeId(null); // Clear code→tree focus
    }
  }, []);

  // Handle clicking a reference node - navigate to target file
  const handleReferenceClick = useCallback((node) => {
    if (node.targetFile && projectData?.files?.[node.targetFile]) {
      setSelectedFile(node.targetFile);
      setHighlightLine(node.targetLine || 1);
      setShowCodePanel(true);
      setFocusedNodeId(null);
    }
  }, [projectData]);

  // Handle clicking a code line - navigate to tree node (code→tree navigation)
  const handleLineClick = useCallback((node) => {
    if (node?.nodeId) {
      setFocusedNodeId(node.nodeId);
      setHighlightLine(node.loc?.start?.line || null);
    }
  }, []);

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
  
  // Build nodesByLine map for code→tree navigation (memoized)
  const nodesByLine = useMemo(() => {
    if (currentTree) {
      return buildNodesByLine(currentTree);
    }
    return {};
  }, [currentTree]);

  // ========================================
  // RENDER
  // ========================================

  return (
    <div className="h-screen flex flex-col bg-slate-900 text-white overflow-hidden">
      {/* ─── Top header bar ─── */}
      <header className="bg-slate-800 border-b border-slate-700 px-4 py-2.5 flex items-center gap-4 shrink-0">
        <h1 className="text-lg font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent flex items-center gap-2 select-none whitespace-nowrap">
          <FirstAidKitIcon size={22} weight="duotone" className="text-blue-400" /> AutoCure AST Visualizer
        </h1>

        <div className="flex-1" />

        {/* Upload buttons */}
        <>
          {projectName && (
            <span className="text-slate-400 text-sm hidden lg:inline">
              {projectName} &bull; {Object.keys(projectData?.files || {}).length} files
            </span>
          )}
          <label className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 rounded-lg text-xs font-medium cursor-pointer transition-colors flex items-center gap-1">
            <UploadIcon size={14} /> ZIP
            <input ref={zipInputRef} type="file" accept=".zip" onChange={handleZipUpload} className="hidden" />
          </label>
          <label className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-xs font-medium cursor-pointer transition-colors flex items-center gap-1">
            <FileArrowUpIcon size={14} /> File
            <input
              ref={fileInputRef}
              type="file"
              accept=".js,.jsx,.ts,.tsx,.mjs,.cjs,.py,.pyw,.java,.kt,.kts,.c,.cpp,.cc,.cxx,.h,.hpp,.hxx,.hh,.cs,.go,.rs,.html,.htm,.css,.vue,.json,.yaml,.yml,.toml,.rb,.erb,.php,.lua,.swift,.scala,.sc,.dart,.ex,.exs,.elm,.zig,.sh,.bash,.zsh,.m,.mm,.ml,.mli,.sol"
              onChange={handleFileUpload}
              className="hidden"
            />
          </label>
        </>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-red-900/70 border-b border-red-700 px-4 py-2 text-red-200 text-sm flex items-center gap-2 shrink-0">
          <WarningCircleIcon size={16} weight="fill" /> <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-auto hover:text-white"><XIcon size={14} /></button>
        </div>
      )}

      {/* ─── AST Visualizer content ─── */}

      {/* AST Visualizer – always visible */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar - Files or Code input */}
        <aside className="w-72 bg-slate-800 border-r border-slate-700 flex flex-col shrink-0">
          {/* Tabs */}
          <div className="flex border-b border-slate-700">
            <button
              onClick={() => mode === "code" ? setMode(projectData ? "project" : "empty") : null}
              className={`flex-1 px-4 py-2 text-sm font-medium flex items-center justify-center gap-1 ${mode !== "code" ? "bg-slate-700 text-blue-400" : "text-slate-400 hover:text-white"}`}
            >
              <FolderOpenIcon size={14} /> Files
            </button>
            <button
              onClick={() => setMode("code")}
              className={`flex-1 px-4 py-2 text-sm font-medium flex items-center justify-center gap-1 ${mode === "code" ? "bg-slate-700 text-blue-400" : "text-slate-400 hover:text-white"}`}
            >
              <PencilSimpleIcon size={14} /> Code
            </button>
          </div>

          {mode === "code" ? (
            /* Code input panel */
            <div className="flex-1 flex flex-col p-3 gap-3 overflow-hidden">
              {/* Language selector */}
              <div className="flex gap-2 items-center">
                <span className="text-xs text-slate-400">Language:</span>
                <select
                  value={codeLanguage}
                  onChange={(e) => setCodeLanguage(e.target.value)}
                  className="bg-slate-900 text-white px-2 py-1 rounded border border-slate-600 text-xs flex-1"
                >
                  <optgroup label="Web">
                    <option value=".js">JavaScript</option>
                    <option value=".ts">TypeScript</option>
                    <option value=".jsx">JSX</option>
                    <option value=".tsx">TSX</option>
                    <option value=".html">HTML</option>
                    <option value=".css">CSS</option>
                    <option value=".vue">Vue</option>
                  </optgroup>
                  <optgroup label="Backend">
                    <option value=".py">Python</option>
                    <option value=".java">Java</option>
                    <option value=".kt">Kotlin</option>
                    <option value=".cs">C#</option>
                    <option value=".go">Go</option>
                    <option value=".rs">Rust</option>
                    <option value=".rb">Ruby</option>
                    <option value=".php">PHP</option>
                    <option value=".scala">Scala</option>
                    <option value=".swift">Swift</option>
                    <option value=".dart">Dart</option>
                    <option value=".ex">Elixir</option>
                  </optgroup>
                  <optgroup label="Systems">
                    <option value=".c">C</option>
                    <option value=".cpp">C++</option>
                    <option value=".h">C Header</option>
                    <option value=".zig">Zig</option>
                    <option value=".m">Objective-C</option>
                  </optgroup>
                  <optgroup label="Functional">
                    <option value=".elm">Elm</option>
                    <option value=".ml">OCaml</option>
                  </optgroup>
                  <optgroup label="Data/Config">
                    <option value=".json">JSON</option>
                    <option value=".yaml">YAML</option>
                    <option value=".toml">TOML</option>
                  </optgroup>
                  <optgroup label="Other">
                    <option value=".lua">Lua</option>
                    <option value=".sh">Bash</option>
                    <option value=".sol">Solidity</option>
                  </optgroup>
                </select>
              </div>
              <textarea
                className="flex-1 bg-slate-900 font-mono text-green-300 p-3 rounded-lg border border-slate-600 text-sm resize-none"
                value={codeInput}
                onChange={(e) => setCodeInput(e.target.value)}
                placeholder="Enter code..."
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
                  <div className="text-4xl mb-3"><FolderOpenIcon size={48} className="mx-auto" /></div>
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
              <span className="text-sm font-mono text-slate-300 flex items-center gap-1"><FileCodeIcon size={14} /> {selectedFile}</span>
            )}
            
            <div className="flex-1" />
            
            {currentContent && (
              <button
                onClick={() => setShowCodePanel(!showCodePanel)}
                className={`px-3 py-1 rounded text-xs font-medium flex items-center gap-1 ${showCodePanel ? 'bg-blue-600' : 'bg-slate-700 hover:bg-slate-600'}`}
              >
                {showCodePanel ? <><EyeSlashIcon size={12} /> Hide Code</> : <><EyeIcon size={12} /> Show Code</>}
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
                <SpinnerGapIcon size={40} className="animate-spin text-blue-400 mx-auto mb-3" />
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
                    focusedNodeId={focusedNodeId}
                  />
                ) : (
                  <div className="h-full flex items-center justify-center text-slate-500">
                    <div className="text-center">
                      <TreeStructureIcon size={64} className="mx-auto mb-4" weight="duotone" />
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
                    onLineClick={handleLineClick}
                    nodesByLine={nodesByLine}
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
  
  // Language icon based on extension using Phosphor icons
  const getIcon = (filename) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    const icons = {
      js: <FileJsIcon size={14} className="text-yellow-400" />,
      mjs: <FileJsIcon size={14} className="text-yellow-400" />,
      cjs: <FileJsIcon size={14} className="text-yellow-400" />,
      jsx: <FileJsIcon size={14} className="text-blue-400" />,
      tsx: <FileTsIcon size={14} className="text-blue-400" />,
      ts: <FileTsIcon size={14} className="text-blue-500" />,
      html: <FileHtmlIcon size={14} className="text-orange-400" />,
      htm: <FileHtmlIcon size={14} className="text-orange-400" />,
      css: <FileCssIcon size={14} className="text-sky-400" />,
      vue: <FileCodeIcon size={14} className="text-green-400" />,
      py: <FilePyIcon size={14} className="text-yellow-300" />,
      pyw: <FilePyIcon size={14} className="text-yellow-300" />,
      java: <FileCodeIcon size={14} className="text-red-400" />,
      kt: <FileCodeIcon size={14} className="text-purple-400" />,
      kts: <FileCodeIcon size={14} className="text-purple-400" />,
      scala: <FileCodeIcon size={14} className="text-red-400" />,
      sc: <FileCodeIcon size={14} className="text-red-400" />,
      c: <FileCIcon size={14} className="text-blue-400" />,
      cpp: <FileCppIcon size={14} className="text-blue-400" />,
      cc: <FileCppIcon size={14} className="text-blue-400" />,
      cxx: <FileCppIcon size={14} className="text-blue-400" />,
      h: <FileCIcon size={14} className="text-slate-400" />,
      hpp: <FileCppIcon size={14} className="text-slate-400" />,
      hxx: <FileCppIcon size={14} className="text-slate-400" />,
      hh: <FileCppIcon size={14} className="text-slate-400" />,
      cs: <FileCodeIcon size={14} className="text-purple-500" />,
      go: <FileCodeIcon size={14} className="text-cyan-400" />,
      rs: <FileRsIcon size={14} className="text-orange-400" />,
      swift: <FileCodeIcon size={14} className="text-orange-500" />,
      dart: <FileCodeIcon size={14} className="text-cyan-500" />,
      zig: <FileCodeIcon size={14} className="text-amber-400" />,
      rb: <FileCodeIcon size={14} className="text-red-500" />,
      erb: <FileCodeIcon size={14} className="text-red-500" />,
      php: <FileCodeIcon size={14} className="text-violet-400" />,
      lua: <FileCodeIcon size={14} className="text-indigo-400" />,
      ex: <FileCodeIcon size={14} className="text-purple-300" />,
      exs: <FileCodeIcon size={14} className="text-purple-300" />,
      elm: <TreeStructureIcon size={14} className="text-green-500" />,
      ml: <FileCodeIcon size={14} className="text-amber-400" />,
      mli: <FileCodeIcon size={14} className="text-amber-400" />,
      sh: <CodeBlockIcon size={14} className="text-green-400" />,
      bash: <CodeBlockIcon size={14} className="text-green-400" />,
      zsh: <CodeBlockIcon size={14} className="text-green-400" />,
      json: <FileIcon size={14} className="text-slate-400" />,
      yaml: <FileIcon size={14} className="text-slate-400" />,
      yml: <FileIcon size={14} className="text-slate-400" />,
      toml: <FileIcon size={14} className="text-slate-400" />,
      m: <FileCodeIcon size={14} className="text-slate-400" />,
      mm: <FileCodeIcon size={14} className="text-slate-400" />,
      sol: <FileCodeIcon size={14} className="text-teal-400" />,
    };
    return icons[ext] || <FileIcon size={14} />;
  };
  
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
      <span className="flex-1 font-mono truncate flex items-center gap-1.5">
        {hasError ? <WarningCircleIcon size={14} className="text-red-400" /> : getIcon(file.name)} {file.name}
      </span>
      {file.language && (
        <span className="px-1 py-0.5 bg-slate-600/50 rounded text-[10px] text-slate-400">
          {file.language}
        </span>
      )}
      {refCount > 0 && (
        <span className="px-1.5 py-0.5 bg-cyan-900/50 rounded text-xs text-cyan-400">
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
      <h3 className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1">
        <LinkIcon size={12} /> References ({outgoing.length + incoming.length})
      </h3>
      <div className="space-y-1">
        {outgoing.map((ref, i) => (
          <button
            key={`out-${i}`}
            onClick={() => onReferenceClick(ref.toFile, ref.toLine)}
            className="w-full text-left px-2 py-1 bg-cyan-900/30 hover:bg-cyan-900/50 rounded text-xs text-cyan-300 flex items-center gap-1"
          >
            <ArrowRightIcon size={10} /> {ref.toFile} <span className="text-slate-500">({ref.toName})</span>
          </button>
        ))}
        {incoming.map((ref, i) => (
          <button
            key={`in-${i}`}
            onClick={() => onReferenceClick(ref.fromFile, ref.fromLine)}
            className="w-full text-left px-2 py-1 bg-amber-900/30 hover:bg-amber-900/50 rounded text-xs text-amber-300 flex items-center gap-1"
          >
            <ArrowLeftIcon size={10} /> {ref.fromFile} <span className="text-slate-500">({ref.fromName})</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export default App;
