const express = require("express");
const cors = require("cors");
const path = require("path");
const multer = require("multer");
const AdmZip = require("adm-zip");

const app = express();
app.use(express.json({ limit: '100mb' }));
app.use(cors());

// Configure multer for file uploads
const storage = multer.memoryStorage();
const upload = multer({ storage, limits: { fileSize: 100 * 1024 * 1024 } });

// ==========================================
// WEB-TREE-SITTER INITIALIZATION
// ==========================================

let Parser;
const languageCache = new Map();
let treeSitterReady = false;

// Path to WASM grammars from tree-sitter-wasms package
const GRAMMARS_DIR = path.join(__dirname, 'node_modules', 'tree-sitter-wasms', 'out');

// Language configuration - map file extensions to WASM grammar files
const LANGUAGE_MAP = {
  // JavaScript/TypeScript
  '.js': { wasm: 'tree-sitter-javascript.wasm', name: 'JavaScript' },
  '.mjs': { wasm: 'tree-sitter-javascript.wasm', name: 'JavaScript' },
  '.cjs': { wasm: 'tree-sitter-javascript.wasm', name: 'JavaScript' },
  '.jsx': { wasm: 'tree-sitter-javascript.wasm', name: 'JavaScript (JSX)' },
  '.ts': { wasm: 'tree-sitter-typescript.wasm', name: 'TypeScript' },
  '.tsx': { wasm: 'tree-sitter-tsx.wasm', name: 'TypeScript (TSX)' },
  
  // Python
  '.py': { wasm: 'tree-sitter-python.wasm', name: 'Python' },
  '.pyw': { wasm: 'tree-sitter-python.wasm', name: 'Python' },
  
  // Java/Kotlin
  '.java': { wasm: 'tree-sitter-java.wasm', name: 'Java' },
  '.kt': { wasm: 'tree-sitter-kotlin.wasm', name: 'Kotlin' },
  '.kts': { wasm: 'tree-sitter-kotlin.wasm', name: 'Kotlin' },
  
  // C/C++
  '.c': { wasm: 'tree-sitter-c.wasm', name: 'C' },
  '.h': { wasm: 'tree-sitter-c.wasm', name: 'C Header' },
  '.cpp': { wasm: 'tree-sitter-cpp.wasm', name: 'C++' },
  '.cc': { wasm: 'tree-sitter-cpp.wasm', name: 'C++' },
  '.cxx': { wasm: 'tree-sitter-cpp.wasm', name: 'C++' },
  '.hpp': { wasm: 'tree-sitter-cpp.wasm', name: 'C++ Header' },
  '.hxx': { wasm: 'tree-sitter-cpp.wasm', name: 'C++ Header' },
  '.hh': { wasm: 'tree-sitter-cpp.wasm', name: 'C++ Header' },
  
  // C#
  '.cs': { wasm: 'tree-sitter-c_sharp.wasm', name: 'C#' },
  
  // Go
  '.go': { wasm: 'tree-sitter-go.wasm', name: 'Go' },
  
  // Rust
  '.rs': { wasm: 'tree-sitter-rust.wasm', name: 'Rust' },
  
  // Web technologies
  '.html': { wasm: 'tree-sitter-html.wasm', name: 'HTML' },
  '.htm': { wasm: 'tree-sitter-html.wasm', name: 'HTML' },
  '.css': { wasm: 'tree-sitter-css.wasm', name: 'CSS' },
  '.vue': { wasm: 'tree-sitter-vue.wasm', name: 'Vue' },
  
  // Data formats
  '.json': { wasm: 'tree-sitter-json.wasm', name: 'JSON' },
  '.yaml': { wasm: 'tree-sitter-yaml.wasm', name: 'YAML' },
  '.yml': { wasm: 'tree-sitter-yaml.wasm', name: 'YAML' },
  '.toml': { wasm: 'tree-sitter-toml.wasm', name: 'TOML' },
  
  // Ruby
  '.rb': { wasm: 'tree-sitter-ruby.wasm', name: 'Ruby' },
  '.erb': { wasm: 'tree-sitter-embedded_template.wasm', name: 'ERB' },
  
  // PHP
  '.php': { wasm: 'tree-sitter-php.wasm', name: 'PHP' },
  
  // Lua
  '.lua': { wasm: 'tree-sitter-lua.wasm', name: 'Lua' },
  
  // Swift
  '.swift': { wasm: 'tree-sitter-swift.wasm', name: 'Swift' },
  
  // Scala
  '.scala': { wasm: 'tree-sitter-scala.wasm', name: 'Scala' },
  '.sc': { wasm: 'tree-sitter-scala.wasm', name: 'Scala' },
  
  // Dart
  '.dart': { wasm: 'tree-sitter-dart.wasm', name: 'Dart' },
  
  // Elixir
  '.ex': { wasm: 'tree-sitter-elixir.wasm', name: 'Elixir' },
  '.exs': { wasm: 'tree-sitter-elixir.wasm', name: 'Elixir' },
  
  // Elm
  '.elm': { wasm: 'tree-sitter-elm.wasm', name: 'Elm' },
  
  // Zig
  '.zig': { wasm: 'tree-sitter-zig.wasm', name: 'Zig' },
  
  // Bash
  '.sh': { wasm: 'tree-sitter-bash.wasm', name: 'Bash' },
  '.bash': { wasm: 'tree-sitter-bash.wasm', name: 'Bash' },
  '.zsh': { wasm: 'tree-sitter-bash.wasm', name: 'Bash' },
  
  // Objective-C
  '.m': { wasm: 'tree-sitter-objc.wasm', name: 'Objective-C' },
  '.mm': { wasm: 'tree-sitter-objc.wasm', name: 'Objective-C++' },
  
  // OCaml
  '.ml': { wasm: 'tree-sitter-ocaml.wasm', name: 'OCaml' },
  '.mli': { wasm: 'tree-sitter-ocaml.wasm', name: 'OCaml' },
  
  // Solidity
  '.sol': { wasm: 'tree-sitter-solidity.wasm', name: 'Solidity' },
};

/**
 * Initialize web-tree-sitter
 */
async function initTreeSitter() {
  try {
    const TreeSitter = require('web-tree-sitter');
    await TreeSitter.init();
    Parser = TreeSitter;
    treeSitterReady = true;
    console.log('   ✓ Tree-sitter WASM initialized');
    return true;
  } catch (err) {
    console.error('Failed to initialize tree-sitter:', err);
    return false;
  }
}

/**
 * Get or load language for parsing
 */
async function getLanguage(filename) {
  const ext = path.extname(filename).toLowerCase();
  const langConfig = LANGUAGE_MAP[ext];
  
  if (!langConfig) {
    return null;
  }
  
  const cacheKey = langConfig.wasm;
  
  if (languageCache.has(cacheKey)) {
    return { language: languageCache.get(cacheKey), name: langConfig.name };
  }
  
  try {
    const wasmPath = path.join(GRAMMARS_DIR, langConfig.wasm);
    const language = await Parser.Language.load(wasmPath);
    languageCache.set(cacheKey, language);
    return { language, name: langConfig.name };
  } catch (err) {
    console.error(`Failed to load language for ${ext}:`, err.message);
    return null;
  }
}

/**
 * Parse code with the appropriate language
 */
async function parseCode(code, filename) {
  if (!treeSitterReady) {
    throw new Error('Tree-sitter not initialized');
  }
  
  const langInfo = await getLanguage(filename);
  if (!langInfo) {
    throw new Error(`Unsupported file type: ${path.extname(filename)}`);
  }
  
  const parser = new Parser();
  parser.setLanguage(langInfo.language);
  const tree = parser.parse(code);
  
  return { tree, language: langInfo.name };
}

/**
 * Get list of supported file extensions
 */
function getSupportedExtensions() {
  return Object.keys(LANGUAGE_MAP);
}

/**
 * Check if a file is supported
 */
function isFileSupported(filename) {
  const ext = path.extname(filename).toLowerCase();
  return LANGUAGE_MAP.hasOwnProperty(ext);
}

// ==========================================
// AST TREE BUILDING
// ==========================================

/**
 * Build visualization tree from tree-sitter node
 */
function buildVisualizationTree(node, sourceCode, depth = 0, maxDepth = 15) {
  if (!node || depth > maxDepth) return null;
  
  const startPos = node.startPosition;
  const endPos = node.endPosition;
  
  const result = {
    id: `${node.type}_${startPos.row}_${startPos.column}_${Math.random().toString(36).slice(2, 8)}`,
    type: node.type,
    name: extractNodeName(node, sourceCode),
    loc: {
      start: { line: startPos.row + 1, column: startPos.column },
      end: { line: endPos.row + 1, column: endPos.column }
    },
    children: [],
    isNamed: node.isNamed,
    fieldName: null
  };
  
  // Get text for small nodes (identifiers, literals, etc.)
  if (node.childCount === 0 && node.text && node.text.length < 100) {
    result.text = node.text;
  }
  
  // Process named children (skip anonymous tokens like punctuation)
  for (let i = 0; i < node.namedChildCount; i++) {
    const child = node.namedChild(i);
    if (child) {
      const childTree = buildVisualizationTree(child, sourceCode, depth + 1, maxDepth);
      if (childTree) {
        // Try to get the field name for this child
        for (const field of getFieldNames(node)) {
          const fieldChild = node.childForFieldName(field);
          if (fieldChild && fieldChild.equals && fieldChild.equals(child)) {
            childTree.fieldName = field;
            break;
          } else if (fieldChild && fieldChild.id === child.id) {
            childTree.fieldName = field;
            break;
          }
        }
        result.children.push(childTree);
      }
    }
  }
  
  return result;
}

/**
 * Get field names for a node type
 */
function getFieldNames(node) {
  // Common field names across languages
  const commonFields = [
    'name', 'body', 'parameters', 'arguments', 'value', 'left', 'right',
    'condition', 'consequence', 'alternative', 'initializer', 'update',
    'declarator', 'type', 'superclass', 'interfaces', 'object', 'property',
    'function', 'callee', 'index', 'key', 'element', 'operand', 'operator',
    'source', 'specifier', 'alias', 'module', 'return_type', 'decorator',
    'receiver', 'field', 'method', 'class', 'expression', 'statement'
  ];
  return commonFields;
}

/**
 * Extract meaningful name from node
 */
function extractNodeName(node, sourceCode) {
  const type = node.type;
  
  // For identifiers, get the text
  if (type === 'identifier' || type === 'property_identifier' || 
      type === 'type_identifier' || type === 'field_identifier') {
    return node.text;
  }
  
  // For function/class declarations, try to find the name child
  const nameChild = node.childForFieldName('name');
  if (nameChild) {
    return nameChild.text;
  }
  
  // For literals, get the value
  if (type.includes('literal') || type === 'string' || type === 'number') {
    const text = node.text;
    if (text && text.length < 50) {
      return text.length > 30 ? text.slice(0, 27) + '...' : text;
    }
  }
  
  return null;
}

/**
 * Find path to a specific line in the tree
 */
function findPathToLine(node, targetLine, path = []) {
  if (!node) return null;
  
  const startLine = node.startPosition.row + 1;
  const endLine = node.endPosition.row + 1;
  
  if (targetLine < startLine || targetLine > endLine) return null;
  
  const currentPath = [...path, {
    type: node.type,
    line: startLine,
    name: node.childForFieldName('name')?.text
  }];
  
  // Check children
  for (let i = 0; i < node.namedChildCount; i++) {
    const child = node.namedChild(i);
    if (child) {
      const found = findPathToLine(child, targetLine, currentPath);
      if (found) return found;
    }
  }
  
  return currentPath;
}

/**
 * Mark error path in tree
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

// ==========================================
// CROSS-FILE REFERENCE DETECTION
// ==========================================

/**
 * Extract imports/requires from AST based on language
 */
function extractImports(tree, sourceCode, language) {
  const imports = [];
  
  function walk(node) {
    if (!node) return;
    
    const type = node.type;
    
    // JavaScript/TypeScript imports
    if (type === 'import_statement' || type === 'import_declaration') {
      const source = node.childForFieldName('source');
      if (source) {
        const sourcePath = source.text.replace(/['"]/g, '');
        const specifiers = [];
        
        // Get import specifiers
        for (let i = 0; i < node.namedChildCount; i++) {
          const child = node.namedChild(i);
          if (child.type === 'import_clause' || child.type === 'import_specifier' || 
              child.type === 'named_imports' || child.type === 'namespace_import') {
            extractSpecifiers(child, specifiers);
          }
        }
        
        imports.push({
          source: sourcePath,
          specifiers: specifiers.length ? specifiers : [{ imported: '*', local: '*' }],
          line: node.startPosition.row + 1,
          isRelative: sourcePath.startsWith('.') || sourcePath.startsWith('/')
        });
      }
    }
    
    // CommonJS require
    if (type === 'call_expression') {
      const callee = node.childForFieldName('function');
      if (callee && callee.text === 'require') {
        const args = node.childForFieldName('arguments');
        if (args && args.namedChildCount > 0) {
          const arg = args.namedChild(0);
          if (arg && (arg.type === 'string' || arg.type === 'string_literal')) {
            const sourcePath = arg.text.replace(/['"]/g, '');
            imports.push({
              source: sourcePath,
              specifiers: [{ imported: '*', local: '*' }],
              line: node.startPosition.row + 1,
              isRelative: sourcePath.startsWith('.') || sourcePath.startsWith('/')
            });
          }
        }
      }
    }
    
    // Python imports
    if (type === 'import_statement' || type === 'import_from_statement') {
      const moduleNode = node.childForFieldName('module_name') || node.childForFieldName('module');
      if (moduleNode) {
        const modulePath = moduleNode.text;
        imports.push({
          source: modulePath,
          specifiers: [{ imported: '*', local: '*' }],
          line: node.startPosition.row + 1,
          isRelative: modulePath.startsWith('.')
        });
      }
    }
    
    // Java imports
    if (type === 'import_declaration') {
      for (let i = 0; i < node.namedChildCount; i++) {
        const child = node.namedChild(i);
        if (child.type === 'scoped_identifier' || child.type === 'identifier') {
          imports.push({
            source: child.text,
            specifiers: [{ imported: child.text.split('.').pop(), local: child.text.split('.').pop() }],
            line: node.startPosition.row + 1,
            isRelative: false
          });
        }
      }
    }
    
    // Go imports
    if (type === 'import_declaration' || type === 'import_spec') {
      const pathNode = node.childForFieldName('path');
      if (pathNode) {
        imports.push({
          source: pathNode.text.replace(/"/g, ''),
          specifiers: [{ imported: '*', local: '*' }],
          line: node.startPosition.row + 1,
          isRelative: pathNode.text.startsWith('"./')
        });
      }
    }
    
    // C/C++ includes
    if (type === 'preproc_include') {
      const pathNode = node.childForFieldName('path');
      if (pathNode) {
        const includePath = pathNode.text.replace(/[<>"]/g, '');
        imports.push({
          source: includePath,
          specifiers: [{ imported: '*', local: '*' }],
          line: node.startPosition.row + 1,
          isRelative: pathNode.text.startsWith('"')
        });
      }
    }
    
    // Rust use statements
    if (type === 'use_declaration') {
      const argument = node.childForFieldName('argument');
      if (argument) {
        imports.push({
          source: argument.text,
          specifiers: [{ imported: '*', local: '*' }],
          line: node.startPosition.row + 1,
          isRelative: argument.text.startsWith('crate::') || argument.text.startsWith('self::') || argument.text.startsWith('super::')
        });
      }
    }
    
    // C# using statements
    if (type === 'using_directive') {
      const nameNode = node.childForFieldName('name');
      if (nameNode) {
        imports.push({
          source: nameNode.text,
          specifiers: [{ imported: '*', local: '*' }],
          line: node.startPosition.row + 1,
          isRelative: false
        });
      }
    }
    
    // Recurse into children
    for (let i = 0; i < node.namedChildCount; i++) {
      walk(node.namedChild(i));
    }
  }
  
  walk(tree.rootNode);
  return imports;
}

/**
 * Extract import specifiers
 */
function extractSpecifiers(node, specifiers) {
  if (!node) return;
  
  if (node.type === 'identifier' || node.type === 'import_specifier') {
    const name = node.childForFieldName('name')?.text || node.text;
    const alias = node.childForFieldName('alias')?.text;
    specifiers.push({
      imported: name,
      local: alias || name
    });
  }
  
  for (let i = 0; i < node.namedChildCount; i++) {
    extractSpecifiers(node.namedChild(i), specifiers);
  }
}

/**
 * Extract exports from AST
 */
function extractExports(tree, sourceCode, language) {
  const exports = [];
  
  function walk(node) {
    if (!node) return;
    
    const type = node.type;
    
    // JavaScript/TypeScript exports
    if (type === 'export_statement' || type === 'export_declaration') {
      const declaration = node.childForFieldName('declaration');
      const nameNode = declaration?.childForFieldName('name');
      exports.push({
        name: nameNode?.text || 'default',
        type: declaration?.type === 'function_declaration' ? 'function' : 'other',
        line: node.startPosition.row + 1,
        isDefault: node.text.includes('export default')
      });
    }
    
    // Recurse
    for (let i = 0; i < node.namedChildCount; i++) {
      walk(node.namedChild(i));
    }
  }
  
  walk(tree.rootNode);
  return exports;
}

/**
 * Extract declarations from AST
 */
function extractDeclarations(tree, sourceCode, language) {
  const declarations = [];
  
  function walk(node, depth = 0) {
    if (!node || depth > 5) return; // Only top-level declarations
    
    const type = node.type;
    const startLine = node.startPosition.row + 1;
    const endLine = node.endPosition.row + 1;
    
    // Function declarations (multiple languages)
    if (type === 'function_declaration' || type === 'function_definition' ||
        type === 'method_definition' || type === 'method_declaration' ||
        type === 'function_item') {
      const nameNode = node.childForFieldName('name');
      if (nameNode) {
        declarations.push({
          name: nameNode.text,
          type: 'function',
          line: startLine,
          endLine: endLine
        });
      }
    }
    
    // Class declarations
    if (type === 'class_declaration' || type === 'class_definition' ||
        type === 'class_specifier' || type === 'struct_item') {
      const nameNode = node.childForFieldName('name');
      if (nameNode) {
        declarations.push({
          name: nameNode.text,
          type: 'class',
          line: startLine,
          endLine: endLine
        });
      }
    }
    
    // Variable declarations
    if (type === 'variable_declaration' || type === 'lexical_declaration' ||
        type === 'const_declaration' || type === 'let_declaration' ||
        type === 'variable_declarator') {
      const nameNode = node.childForFieldName('name');
      if (nameNode) {
        declarations.push({
          name: nameNode.text,
          type: 'variable',
          line: startLine,
          endLine: endLine
        });
      }
    }
    
    // Recurse into top-level children only
    if (depth === 0 || type === 'program' || type === 'module' || type === 'translation_unit') {
      for (let i = 0; i < node.namedChildCount; i++) {
        walk(node.namedChild(i), depth + 1);
      }
    }
  }
  
  walk(tree.rootNode);
  return declarations;
}

/**
 * Resolve import path to actual file
 */
function resolveImportPath(currentFile, importPath, availableFiles, language) {
  // Skip non-relative imports for most languages
  if (!importPath.startsWith('.') && !importPath.startsWith('/')) {
    // Special handling for certain languages
    if (language === 'Python') {
      // Python relative imports
      if (!importPath.startsWith('.')) return null;
    } else {
      return null;
    }
  }
  
  const currentDir = path.dirname(currentFile);
  let resolved = path.posix.join(currentDir, importPath).replace(/\\/g, '/');
  
  // Remove leading ./ or /
  if (resolved.startsWith('./')) resolved = resolved.slice(2);
  if (resolved.startsWith('/')) resolved = resolved.slice(1);
  
  // Try exact match
  if (availableFiles.includes(resolved)) return resolved;
  
  // Try with common extensions
  const extensions = getSupportedExtensions();
  for (const ext of extensions) {
    if (availableFiles.includes(resolved + ext)) return resolved + ext;
  }
  
  // Try index files
  for (const ext of extensions) {
    if (availableFiles.includes(`${resolved}/index${ext}`)) return `${resolved}/index${ext}`;
  }
  
  // Python: try __init__.py
  if (availableFiles.includes(`${resolved}/__init__.py`)) return `${resolved}/__init__.py`;
  
  return null;
}

/**
 * Build complete project visualization map
 */
async function buildProjectVisualization(files) {
  const fileNames = files.map(f => f.name);
  const fileData = new Map();
  const crossReferences = [];
  
  // First pass: Parse all files
  for (const file of files) {
    try {
      const { tree, language } = await parseCode(file.content, file.name);
      const vizTree = buildVisualizationTree(tree.rootNode, file.content);
      const imports = extractImports(tree, file.content, language);
      const exports = extractExports(tree, file.content, language);
      const declarations = extractDeclarations(tree, file.content, language);
      
      fileData.set(file.name, {
        name: file.name,
        content: file.content,
        tree: vizTree,
        imports,
        exports,
        declarations,
        language,
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
        language: 'Unknown',
        error: err.message
      });
    }
  }
  
  // Second pass: Build cross-file references
  for (const [fileName, data] of fileData) {
    if (!data.imports) continue;
    
    for (const imp of data.imports) {
      if (!imp.isRelative) continue;
      
      const targetFile = resolveImportPath(fileName, imp.source, fileNames, data.language);
      if (!targetFile) continue;
      
      const targetData = fileData.get(targetFile);
      if (!targetData) continue;
      
      // Create reference entry
      for (const spec of imp.specifiers) {
        const importedName = spec.imported || 'default';
        
        // Find matching export/declaration in target file
        let targetLine = 1;
        const targetExport = targetData.exports?.find(e => e.name === importedName || (importedName === '*' && e.isDefault));
        if (targetExport) {
          targetLine = targetExport.line;
        } else {
          const targetDecl = targetData.declarations?.find(d => d.name === importedName);
          if (targetDecl) targetLine = targetDecl.line;
        }
        
        crossReferences.push({
          id: `ref_${fileName}_${imp.line}_${targetFile}_${Math.random().toString(36).slice(2, 6)}`,
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
  
  // Mark reference nodes in trees
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
      totalReferences: crossReferences.length,
      languages: [...new Set([...fileData.values()].map(f => f.language).filter(Boolean))]
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
      language: data.language,
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
app.post("/upload/zip", upload.single('file'), async (req, res) => {
  console.log("Received ZIP upload request");
  
  try {
    if (!treeSitterReady) {
      return res.status(503).json({ error: "Tree-sitter not yet initialized" });
    }
    
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
          filename.includes('__pycache__/') ||
          filename.includes('.venv/') ||
          filename.includes('venv/') ||
          filename.includes('target/') ||
          filename.includes('build/') ||
          filename.includes('dist/') ||
          filename.startsWith('__MACOSX/') ||
          filename.includes('.DS_Store')) {
        continue;
      }
      
      // Only process supported files
      if (isFileSupported(filename)) {
        try {
          const content = entry.getData().toString('utf-8');
          files.push({ name: filename, content });
        } catch (e) {
          console.warn(`Skipping binary file: ${filename}`);
        }
      }
    }
    
    if (files.length === 0) {
      return res.status(400).json({ 
        error: "No supported source files found in ZIP",
        supportedExtensions: getSupportedExtensions()
      });
    }
    
    console.log(`Processing ${files.length} files from ZIP`);
    
    // Build complete visualization
    const visualization = await buildProjectVisualization(files);
    visualization.projectName = req.file.originalname.replace('.zip', '');
    visualization.supportedExtensions = getSupportedExtensions();
    
    console.log(`Visualization built: ${visualization.summary.totalFiles} files, ${visualization.summary.totalReferences} references, languages: ${visualization.summary.languages.join(', ')}`);
    
    res.json(visualization);
    
  } catch (err) {
    console.error("ZIP processing error:", err);
    res.status(500).json({ error: err.message });
  }
});

/**
 * POST /upload/file - Upload a single file for visualization
 */
app.post("/upload/file", upload.single('file'), async (req, res) => {
  console.log("Received file upload request");
  
  try {
    if (!treeSitterReady) {
      return res.status(503).json({ error: "Tree-sitter not yet initialized" });
    }
    
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }
    
    const filename = req.file.originalname;
    const content = req.file.buffer.toString('utf-8');
    
    const { tree, language } = await parseCode(content, filename);
    const vizTree = buildVisualizationTree(tree.rootNode, content);
    const declarations = extractDeclarations(tree, content, language);
    
    res.json({
      filename,
      content,
      tree: vizTree,
      declarations,
      language,
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
app.post("/parse/code", async (req, res) => {
  const { code, errorLine, filename = "code.js", language: requestedLang } = req.body;
  
  if (!code) {
    return res.status(400).json({ error: "Code is required" });
  }
  
  try {
    if (!treeSitterReady) {
      return res.status(503).json({ error: "Tree-sitter not yet initialized" });
    }
    
    const { tree, language } = await parseCode(code, filename);
    const vizTree = buildVisualizationTree(tree.rootNode, code);
    
    let errorPath = null;
    if (typeof errorLine === 'number' && errorLine > 0) {
      errorPath = findPathToLine(tree.rootNode, errorLine);
      if (errorPath) {
        markErrorPath(vizTree, errorPath);
      }
    }
    
    res.json({
      filename,
      content: code,
      tree: vizTree,
      errorLine: errorLine || null,
      errorPath,
      language,
      declarations: extractDeclarations(tree, code, language)
    });
    
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

/**
 * GET /languages - Get list of supported languages
 */
app.get("/languages", (req, res) => {
  const languages = {};
  for (const [ext, config] of Object.entries(LANGUAGE_MAP)) {
    if (!languages[config.name]) {
      languages[config.name] = [];
    }
    languages[config.name].push(ext);
  }
  res.json({ languages, extensions: getSupportedExtensions() });
});

/**
 * Health check endpoint
 */
app.get("/health", (req, res) => {
  res.json({ 
    status: treeSitterReady ? "ok" : "initializing", 
    timestamp: new Date().toISOString(),
    supportedLanguages: [...new Set(Object.values(LANGUAGE_MAP).map(l => l.name))]
  });
});

// Start server
const PORT = process.env.PORT || 3000;

async function startServer() {
  console.log(`\n🌳 AST Visualization Server (Web-Tree-sitter)`);
  console.log(`   Initializing...\n`);
  
  await initTreeSitter();
  
  console.log(`\n   Supported Languages (${Object.keys(LANGUAGE_MAP).length} extensions):`);
  const langs = [...new Set(Object.values(LANGUAGE_MAP).map(l => l.name))].sort();
  const columns = 3;
  for (let i = 0; i < langs.length; i += columns) {
    const row = langs.slice(i, i + columns).map(l => `   • ${l.padEnd(18)}`).join('');
    console.log(row);
  }
  
  app.listen(PORT, () => {
    console.log(`\n   Server running on http://localhost:${PORT}`);
    console.log(`\n   Endpoints:`);
    console.log(`   POST /upload/zip   - Upload ZIP project`);
    console.log(`   POST /upload/file  - Upload single file`);
    console.log(`   POST /parse/code   - Parse code snippet`);
    console.log(`   GET  /languages    - List supported languages`);
    console.log(`   GET  /health       - Health check\n`);
  });
}

startServer().catch(console.error);
