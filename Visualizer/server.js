const express = require("express");
const parser = require("@babel/parser");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const multer = require("multer");
const AdmZip = require("adm-zip");

const app = express();
app.use(express.json({ limit: '100mb' }));
app.use(cors());

// Configure multer for file uploads
const storage = multer.memoryStorage();
const upload = multer({ storage, limits: { fileSize: 100 * 1024 * 1024 } });

// Supported file extensions
const SUPPORTED_EXTENSIONS = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'];

// ==========================================
// AST PARSING FUNCTIONS
// ==========================================

/**
 * Parse code into AST with error recovery
 */
function parseCode(code, filename = "unknown.js") {
  const isTypeScript = filename.endsWith('.ts') || filename.endsWith('.tsx');
  const isJSX = filename.endsWith('.jsx') || filename.endsWith('.tsx');
  
  const plugins = ['decorators-legacy', 'classProperties'];
  if (isJSX || filename.endsWith('.js')) plugins.push('jsx');
  if (isTypeScript) plugins.push('typescript');

  return parser.parse(code, {
    sourceType: "module",
    plugins,
    errorRecovery: true
  });
}

/**
 * Build a complete tree structure for visualization
 * This is the FULL tree that will be sent to frontend
 */
function buildVisualizationTree(node, depth = 0, maxDepth = 10) {
  if (!node || typeof node !== "object" || depth > maxDepth) return null;
  if (!node.type) return null;

  const result = {
    id: `${node.type}_${node.loc?.start?.line || 0}_${node.loc?.start?.column || 0}_${Math.random().toString(36).slice(2, 8)}`,
    type: node.type,
    name: extractNodeName(node),
    loc: node.loc ? {
      start: { line: node.loc.start.line, column: node.loc.start.column },
      end: { line: node.loc.end.line, column: node.loc.end.column }
    } : null,
    children: []
  };

  // Add extra info for certain node types
  if (node.type === 'ImportDeclaration' && node.source?.value) {
    result.source = node.source.value;
    result.specifiers = (node.specifiers || []).map(s => s.local?.name || s.imported?.name).filter(Boolean);
  }
  if (node.type === 'ExportNamedDeclaration' || node.type === 'ExportDefaultDeclaration') {
    result.isExport = true;
  }
  if (node.type === 'CallExpression' && node.callee) {
    result.callee = node.callee.name || (node.callee.property?.name ? `*.${node.callee.property.name}` : null);
  }
  if (node.type === 'Literal' || node.type === 'StringLiteral' || node.type === 'NumericLiteral') {
    result.value = String(node.value).slice(0, 50);
  }

  // Process children based on node type
  const childKeys = getChildKeys(node);
  for (const key of childKeys) {
    const value = node[key];
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item && typeof item === 'object' && item.type) {
          const child = buildVisualizationTree(item, depth + 1, maxDepth);
          if (child) result.children.push(child);
        }
      }
    } else if (value && typeof value === 'object' && value.type) {
      const child = buildVisualizationTree(value, depth + 1, maxDepth);
      if (child) result.children.push(child);
    }
  }

  return result;
}

/**
 * Extract meaningful name from node
 */
function extractNodeName(node) {
  if (node.id?.name) return node.id.name;
  if (node.key?.name) return node.key.name;
  if (node.name) return node.name;
  if (node.property?.name) return node.property.name;
  if (node.declaration?.id?.name) return node.declaration.id.name;
  if (node.declarations?.[0]?.id?.name) return node.declarations[0].id.name;
  return null;
}

/**
 * Get child property keys for a node type
 */
function getChildKeys(node) {
  const skipKeys = new Set(['loc', 'start', 'end', 'range', 'comments', 'leadingComments', 'trailingComments', 'extra', 'raw']);
  const keys = [];
  
  for (const key of Object.keys(node)) {
    if (skipKeys.has(key)) continue;
    const value = node[key];
    if (value && typeof value === 'object') {
      if (Array.isArray(value) && value.some(v => v?.type)) {
        keys.push(key);
      } else if (value.type) {
        keys.push(key);
      }
    }
  }
  return keys;
}

/**
 * Find path to a specific line in AST
 */
function findPathToLine(node, targetLine, path = []) {
  if (!node || !node.loc) return null;
  
  const { start, end } = node.loc;
  if (targetLine < start.line || targetLine > end.line) return null;

  const currentPath = [...path, {
    id: node.id || `${node.type}_${start.line}`,
    type: node.type,
    line: start.line
  }];

  // Check children
  const childKeys = getChildKeys(node);
  for (const key of childKeys) {
    const value = node[key];
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item?.type) {
          const found = findPathToLine(item, targetLine, currentPath);
          if (found) return found;
        }
      }
    } else if (value?.type) {
      const found = findPathToLine(value, targetLine, currentPath);
      if (found) return found;
    }
  }

  return currentPath;
}

// ==========================================
// REFERENCE & CROSS-FILE ANALYSIS
// ==========================================

/**
 * Extract all imports from AST
 */
function extractImports(ast) {
  const imports = [];
  const body = ast.program?.body || ast.body || [];
  
  for (const node of body) {
    if (node.type === 'ImportDeclaration' && node.source?.value) {
      imports.push({
        source: node.source.value,
        specifiers: (node.specifiers || []).map(s => ({
          imported: s.imported?.name || s.local?.name,
          local: s.local?.name,
          type: s.type
        })),
        line: node.loc?.start?.line || 0,
        isRelative: node.source.value.startsWith('.') || node.source.value.startsWith('/')
      });
    }
  }
  return imports;
}

/**
 * Extract all exports from AST
 */
function extractExports(ast) {
  const exports = [];
  const body = ast.program?.body || ast.body || [];
  
  for (const node of body) {
    if (node.type === 'ExportNamedDeclaration') {
      if (node.declaration) {
        const name = node.declaration.id?.name || node.declaration.declarations?.[0]?.id?.name;
        if (name) exports.push({ name, type: 'named', line: node.loc?.start?.line });
      }
      for (const spec of node.specifiers || []) {
        exports.push({ name: spec.exported?.name, type: 'named', line: node.loc?.start?.line });
      }
    } else if (node.type === 'ExportDefaultDeclaration') {
      const name = node.declaration?.id?.name || 'default';
      exports.push({ name, type: 'default', line: node.loc?.start?.line, isDefault: true });
    }
  }
  return exports;
}

/**
 * Extract top-level declarations
 */
function extractDeclarations(ast) {
  const declarations = [];
  const body = ast.program?.body || ast.body || [];
  
  for (const node of body) {
    if (node.type === 'FunctionDeclaration' && node.id?.name) {
      declarations.push({
        name: node.id.name,
        type: 'function',
        line: node.loc?.start?.line,
        endLine: node.loc?.end?.line
      });
    } else if (node.type === 'ClassDeclaration' && node.id?.name) {
      declarations.push({
        name: node.id.name,
        type: 'class',
        line: node.loc?.start?.line,
        endLine: node.loc?.end?.line
      });
    } else if (node.type === 'VariableDeclaration') {
      for (const decl of node.declarations || []) {
        if (decl.id?.name) {
          declarations.push({
            name: decl.id.name,
            type: decl.init?.type === 'ArrowFunctionExpression' || decl.init?.type === 'FunctionExpression' ? 'function' : 'variable',
            line: decl.loc?.start?.line,
            endLine: decl.loc?.end?.line
          });
        }
      }
    } else if (node.type === 'ExportNamedDeclaration' && node.declaration) {
      if (node.declaration.type === 'FunctionDeclaration' && node.declaration.id?.name) {
        declarations.push({
          name: node.declaration.id.name,
          type: 'function',
          line: node.declaration.loc?.start?.line,
          endLine: node.declaration.loc?.end?.line,
          exported: true
        });
      } else if (node.declaration.type === 'VariableDeclaration') {
        for (const decl of node.declaration.declarations || []) {
          if (decl.id?.name) {
            declarations.push({
              name: decl.id.name,
              type: 'variable',
              line: decl.loc?.start?.line,
              endLine: decl.loc?.end?.line,
              exported: true
            });
          }
        }
      }
    } else if (node.type === 'ExportDefaultDeclaration' && node.declaration) {
      const name = node.declaration.id?.name || 'default';
      declarations.push({
        name,
        type: node.declaration.type === 'FunctionDeclaration' ? 'function' : 'class',
        line: node.loc?.start?.line,
        endLine: node.loc?.end?.line,
        exported: true,
        isDefault: true
      });
    }
  }
  return declarations;
}

/**
 * Resolve import path to actual file
 */
function resolveImportPath(currentFile, importPath, availableFiles) {
  // Skip non-relative imports
  if (!importPath.startsWith('.') && !importPath.startsWith('/')) {
    return null;
  }

  const currentDir = path.dirname(currentFile);
  let resolved = path.posix.join(currentDir, importPath).replace(/\\/g, '/');
  
  // Remove leading ./ or /
  if (resolved.startsWith('./')) resolved = resolved.slice(2);
  if (resolved.startsWith('/')) resolved = resolved.slice(1);
  
  // Try exact match
  if (availableFiles.includes(resolved)) return resolved;
  
  // Try with extensions
  for (const ext of SUPPORTED_EXTENSIONS) {
    if (availableFiles.includes(resolved + ext)) return resolved + ext;
  }
  
  // Try index files
  for (const ext of SUPPORTED_EXTENSIONS) {
    if (availableFiles.includes(`${resolved}/index${ext}`)) return `${resolved}/index${ext}`;
  }
  
  return null;
}

/**
 * Build complete project visualization map
 * This is the main function that creates the full visualization data
 */
function buildProjectVisualization(files) {
  const fileNames = files.map(f => f.name);
  const fileData = new Map();
  const crossReferences = [];

  // First pass: Parse all files
  for (const file of files) {
    try {
      const ast = parseCode(file.content, file.name);
      const tree = buildVisualizationTree(ast.program, 0, 12);
      const imports = extractImports(ast);
      const exports = extractExports(ast);
      const declarations = extractDeclarations(ast);

      fileData.set(file.name, {
        name: file.name,
        content: file.content,
        tree,
        imports,
        exports,
        declarations,
        error: null
      });
    } catch (err) {
      fileData.set(file.name, {
        name: file.name,
        content: file.content,
        tree: null,
        imports: [],
        exports: [],
        declarations: [],
        error: err.message
      });
    }
  }

  // Second pass: Build cross-file references
  for (const [fileName, data] of fileData) {
    if (!data.imports) continue;

    for (const imp of data.imports) {
      if (!imp.isRelative) continue;
      
      const targetFile = resolveImportPath(fileName, imp.source, fileNames);
      if (!targetFile) continue;

      const targetData = fileData.get(targetFile);
      if (!targetData) continue;

      // Create reference entry
      for (const spec of imp.specifiers) {
        const importedName = spec.imported || 'default';
        
        // Find matching export/declaration in target file
        let targetLine = null;
        const targetExport = targetData.exports.find(e => e.name === importedName || (importedName === 'default' && e.isDefault));
        if (targetExport) {
          targetLine = targetExport.line;
        } else {
          const targetDecl = targetData.declarations.find(d => d.name === importedName);
          if (targetDecl) targetLine = targetDecl.line;
        }

        crossReferences.push({
          id: `ref_${fileName}_${imp.line}_${targetFile}`,
          fromFile: fileName,
          fromLine: imp.line,
          fromName: spec.local || importedName,
          toFile: targetFile,
          toLine: targetLine,
          toName: importedName,
          type: 'import'
        });
      }
    }
  }

  // Mark nodes that have cross-references
  for (const ref of crossReferences) {
    const fromData = fileData.get(ref.fromFile);
    if (fromData?.tree) {
      markReferenceNode(fromData.tree, ref.fromLine, {
        isReference: true,
        referenceId: ref.id,
        direction: 'outgoing',
        targetFile: ref.toFile,
        targetLine: ref.toLine,
        targetName: ref.toName
      });
    }
  }

  // Build final result
  const result = {
    files: {},
    references: crossReferences,
    summary: {
      totalFiles: files.length,
      totalReferences: crossReferences.length
    }
  };

  for (const [fileName, data] of fileData) {
    result.files[fileName] = {
      name: data.name,
      content: data.content,
      tree: data.tree,
      declarations: data.declarations,
      imports: data.imports,
      exports: data.exports,
      error: data.error,
      incomingRefs: crossReferences.filter(r => r.toFile === fileName),
      outgoingRefs: crossReferences.filter(r => r.fromFile === fileName)
    };
  }

  return result;
}

/**
 * Mark a node at specific line as a reference
 */
function markReferenceNode(tree, line, refInfo) {
  if (!tree) return false;
  
  if (tree.loc?.start?.line === line) {
    Object.assign(tree, refInfo);
    return true;
  }
  
  if (tree.children) {
    for (const child of tree.children) {
      if (markReferenceNode(child, line, refInfo)) return true;
    }
  }
  
  return false;
}

// ==========================================
// API ENDPOINTS
// ==========================================

/**
 * POST /upload/zip - Upload a ZIP file and get complete visualization map
 */
app.post("/upload/zip", upload.single('file'), (req, res) => {
  console.log("Received ZIP upload request");
  
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const zip = new AdmZip(req.file.buffer);
    const files = [];
    let rootFolder = '';

    // Find common root folder in ZIP
    const entries = zip.getEntries();
    for (const entry of entries) {
      if (!entry.isDirectory) {
        const parts = entry.entryName.split('/');
        if (parts.length > 1 && !rootFolder) {
          rootFolder = parts[0] + '/';
        }
        break;
      }
    }

    // Extract files
    for (const entry of entries) {
      if (entry.isDirectory) continue;
      
      let filename = entry.entryName.replace(/\\/g, '/');
      
      // Remove common root folder prefix
      if (rootFolder && filename.startsWith(rootFolder)) {
        filename = filename.slice(rootFolder.length);
      }
      
      // Skip unwanted files
      if (filename.includes('node_modules/') || 
          filename.includes('.git/') ||
          filename.startsWith('__MACOSX/') ||
          filename.includes('.DS_Store')) {
        continue;
      }

      // Only process supported files
      if (SUPPORTED_EXTENSIONS.some(ext => filename.endsWith(ext))) {
        const content = entry.getData().toString('utf-8');
        files.push({ name: filename, content });
      }
    }

    if (files.length === 0) {
      return res.status(400).json({ error: "No JavaScript/TypeScript files found in ZIP" });
    }

    console.log(`Processing ${files.length} files from ZIP`);

    // Build complete visualization
    const visualization = buildProjectVisualization(files);
    visualization.projectName = req.file.originalname.replace('.zip', '');

    console.log(`Visualization built: ${visualization.summary.totalFiles} files, ${visualization.summary.totalReferences} references`);

    res.json(visualization);

  } catch (err) {
    console.error("ZIP processing error:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /upload/file - Upload a single file for visualization
 */
app.post("/upload/file", upload.single('file'), (req, res) => {
  console.log("Received file upload request");
  
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    const filename = req.file.originalname;
    const content = req.file.buffer.toString('utf-8');

    const ast = parseCode(content, filename);
    const tree = buildVisualizationTree(ast.program, 0, 15);
    const declarations = extractDeclarations(ast);

    res.json({
      filename,
      content,
      tree,
      declarations,
      error: null
    });

  } catch (err) {
    console.error("File processing error:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /parse/code - Parse code snippet with optional error line
 */
app.post("/parse/code", (req, res) => {
  const { code, errorLine, filename = "code.js" } = req.body;
  
  if (!code) {
    return res.status(400).json({ error: "Code is required" });
  }

  try {
    const ast = parseCode(code, filename);
    const tree = buildVisualizationTree(ast.program, 0, 15);
    
    let errorPath = null;
    if (typeof errorLine === 'number' && errorLine > 0) {
      errorPath = findPathToLine(ast.program, errorLine);
      // Mark error nodes in tree
      if (errorPath) {
        markErrorPath(tree, errorPath);
      }
    }

    res.json({
      filename,
      content: code,
      tree,
      errorLine: errorLine || null,
      errorPath,
      declarations: extractDeclarations(ast)
    });

  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/**
 * Mark nodes in error path
 */
function markErrorPath(tree, errorPath) {
  if (!tree || !errorPath) return;
  
  const errorLines = new Set(errorPath.map(p => p.line));
  
  function mark(node) {
    if (!node) return;
    if (node.loc?.start?.line && errorLines.has(node.loc.start.line)) {
      node.isError = true;
    }
    if (node.children) {
      node.children.forEach(mark);
    }
  }
  
  mark(tree);
}

/**
 * Health check endpoint
 */
app.get("/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`\n🌳 AST Visualization Server`);
  console.log(`   Running on http://localhost:${PORT}`);
  console.log(`\n   Endpoints:`);
  console.log(`   POST /upload/zip   - Upload ZIP project`);
  console.log(`   POST /upload/file  - Upload single file`);
  console.log(`   POST /parse/code   - Parse code snippet`);
  console.log(`   GET  /health       - Health check\n`);
});
