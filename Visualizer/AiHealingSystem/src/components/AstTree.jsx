import React, { useState, useCallback, memo } from "react";
import { TreeStructureIcon } from "@phosphor-icons/react";

// Lightweight custom tree component - NO react-d3-tree
const ASTTree = memo(({ ast, highlightPath = [], references = [], onReferenceClick }) => {
  const [expandedNodes, setExpandedNodes] = useState(new Set(['root']));

  const highlightSet = new Set(
    highlightPath.map(n => `${n.type}:${n.loc?.start?.line || 0}`)
  );

  const toggleNode = useCallback((nodeId) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }, []);

  const expandAll = () => {
    const ids = new Set(['root']);
    const collect = (node, prefix = 'root') => {
      if (node?.children) {
        node.children.forEach((child, i) => {
          const id = `${prefix}-${i}`;
          ids.add(id);
          collect(child, id);
        });
      }
    };
    collect(ast);
    setExpandedNodes(ids);
  };

  const collapseAll = () => setExpandedNodes(new Set(['root']));

  if (!ast) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400">
        <div className="text-center">
          <TreeStructureIcon size={48} weight="duotone" className="mb-2 opacity-50" />
          <p>Select a file to view its AST</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex gap-2 p-2 bg-slate-800 border-b border-slate-700">
        <button onClick={expandAll} className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs">
          Expand All
        </button>
        <button onClick={collapseAll} className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs">
          Collapse All
        </button>
      </div>
      <div className="flex-1 overflow-auto p-4 font-mono text-sm">
        <TreeNode 
          node={ast} 
          nodeId="root"
          depth={0}
          expandedNodes={expandedNodes}
          toggleNode={toggleNode}
          highlightSet={highlightSet}
          onReferenceClick={onReferenceClick}
        />
      </div>
    </div>
  );
});

// Individual tree node - memoized for performance
const TreeNode = memo(({ node, nodeId, depth, expandedNodes, toggleNode, highlightSet, onReferenceClick }) => {
  if (!node) return null;

  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = expandedNodes.has(nodeId);
  const nodeKey = `${node.type}:${node.loc?.start?.line || 0}`;
  const isHighlighted = highlightSet.has(nodeKey);
  const isReference = node.isReference;

  // Determine colors
  let bgColor = 'bg-slate-700';
  let borderColor = 'border-slate-600';
  let textColor = 'text-white';
  
  if (isHighlighted) {
    bgColor = 'bg-red-600';
    borderColor = 'border-red-400';
  } else if (isReference) {
    if (node.direction === 'outgoing') {
      bgColor = 'bg-cyan-700';
      borderColor = 'border-cyan-500';
    } else {
      bgColor = 'bg-amber-700';
      borderColor = 'border-amber-500';
    }
  }

  const handleClick = () => {
    if (isReference && node.targetFile && onReferenceClick) {
      onReferenceClick(node.targetFile, node.loc?.start?.line);
    }
  };

  // Build display name
  let displayName = node.type;
  if (node.name) displayName += ` (${node.name})`;
  if (node.names?.length) displayName += ` [${node.names.join(', ')}]`;
  if (node.source) displayName += ` "${node.source}"`;

  return (
    <div style={{ marginLeft: depth > 0 ? 20 : 0 }}>
      <div 
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded border ${bgColor} ${borderColor} mb-1 ${isReference ? 'cursor-pointer hover:opacity-80' : ''}`}
        onClick={isReference ? handleClick : undefined}
      >
        {hasChildren && (
          <button 
            onClick={(e) => { e.stopPropagation(); toggleNode(nodeId); }}
            className="w-4 h-4 flex items-center justify-center bg-slate-600 rounded text-xs hover:bg-slate-500"
          >
            {isExpanded ? '−' : '+'}
          </button>
        )}
        
        <span className={textColor}>{displayName}</span>
        
        {node.loc && (
          <span className="text-slate-400 text-xs">L{node.loc.start.line}</span>
        )}
        
        {isReference && (
          <span className={`text-xs ${node.direction === 'outgoing' ? 'text-cyan-300' : 'text-amber-300'}`}>
            {node.direction === 'outgoing' ? '→' : '←'} {node.targetFile?.split('/').pop()}
          </span>
        )}
        
        {node.truncated && (
          <span className="text-yellow-400 text-xs">...</span>
        )}
      </div>

      {hasChildren && isExpanded && (
        <div className="border-l border-slate-600 ml-2">
          {node.children.map((child, i) => (
            <TreeNode
              key={`${nodeId}-${i}`}
              node={child}
              nodeId={`${nodeId}-${i}`}
              depth={depth + 1}
              expandedNodes={expandedNodes}
              toggleNode={toggleNode}
              highlightSet={highlightSet}
              onReferenceClick={onReferenceClick}
            />
          ))}
        </div>
      )}
    </div>
  );
});

export default ASTTree;
