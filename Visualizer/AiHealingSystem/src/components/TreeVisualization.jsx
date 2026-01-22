import React, { useState, useCallback, memo, useRef, useEffect } from "react";

/**
 * TreeVisualization - Renders AST as an interactive tree graph
 * Uses SVG for proper tree visualization with lines
 */
const TreeVisualization = memo(({ tree, onNodeClick, onReferenceClick }) => {
  const [expandedNodes, setExpandedNodes] = useState(new Set(['root']));
  const [transform, setTransform] = useState({ x: 50, y: 20, scale: 1 });
  const containerRef = useRef(null);
  const isDragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });

  // Initialize with first level expanded
  useEffect(() => {
    if (tree) {
      const initial = new Set(['root']);
      if (tree.children) {
        tree.children.forEach((_, i) => initial.add(`root-${i}`));
      }
      setExpandedNodes(initial);
    }
  }, [tree]);

  const toggleNode = useCallback((nodeId) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        // Collapse: remove this node and all children
        for (const id of next) {
          if (id.startsWith(nodeId + '-')) next.delete(id);
        }
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    const all = new Set(['root']);
    const collect = (node, prefix) => {
      if (node?.children) {
        node.children.forEach((child, i) => {
          const id = `${prefix}-${i}`;
          all.add(id);
          collect(child, id);
        });
      }
    };
    collect(tree, 'root');
    setExpandedNodes(all);
  }, [tree]);

  const collapseAll = useCallback(() => {
    setExpandedNodes(new Set(['root']));
  }, []);

  // Pan handlers
  const handleMouseDown = (e) => {
    if (e.target === containerRef.current || e.target.tagName === 'svg') {
      isDragging.current = true;
      lastPos.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleMouseMove = (e) => {
    if (isDragging.current) {
      const dx = e.clientX - lastPos.current.x;
      const dy = e.clientY - lastPos.current.y;
      setTransform(prev => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
      lastPos.current = { x: e.clientX, y: e.clientY };
    }
  };

  const handleMouseUp = () => {
    isDragging.current = false;
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setTransform(prev => ({
      ...prev,
      scale: Math.max(0.2, Math.min(3, prev.scale * delta))
    }));
  };

  if (!tree) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500">
        <div className="text-center">
          <div className="text-6xl mb-4">🌳</div>
          <p>No tree data</p>
        </div>
      </div>
    );
  }

  // Calculate tree layout
  const { nodes, edges, width, height } = layoutTree(tree, expandedNodes);

  return (
    <div className="h-full flex flex-col bg-slate-900">
      {/* Controls */}
      <div className="flex items-center gap-2 p-2 bg-slate-800 border-b border-slate-700 shrink-0">
        <button
          onClick={expandAll}
          className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs"
        >
          Expand All
        </button>
        <button
          onClick={collapseAll}
          className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs"
        >
          Collapse All
        </button>
        <span className="text-slate-500 text-xs mx-2">|</span>
        <button
          onClick={() => setTransform(prev => ({ ...prev, scale: Math.min(3, prev.scale * 1.2) }))}
          className="w-7 h-7 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center text-sm"
        >
          +
        </button>
        <button
          onClick={() => setTransform(prev => ({ ...prev, scale: Math.max(0.2, prev.scale * 0.8) }))}
          className="w-7 h-7 bg-slate-700 hover:bg-slate-600 rounded flex items-center justify-center text-sm"
        >
          −
        </button>
        <button
          onClick={() => setTransform({ x: 50, y: 20, scale: 1 })}
          className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs"
        >
          Reset
        </button>
        <span className="text-slate-500 text-xs ml-2">
          {Math.round(transform.scale * 100)}%
        </span>
        <span className="text-slate-500 text-xs ml-auto">
          Drag to pan • Scroll to zoom • Click nodes to view code
        </span>
      </div>

      {/* SVG Canvas */}
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        <svg
          width="100%"
          height="100%"
          style={{ minWidth: '100%', minHeight: '100%' }}
        >
          <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.scale})`}>
            {/* Draw edges first (behind nodes) */}
            {edges.map((edge, i) => (
              <path
                key={`edge-${i}`}
                d={`M ${edge.x1} ${edge.y1} C ${edge.x1} ${(edge.y1 + edge.y2) / 2}, ${edge.x2} ${(edge.y1 + edge.y2) / 2}, ${edge.x2} ${edge.y2}`}
                fill="none"
                stroke="#475569"
                strokeWidth="2"
              />
            ))}

            {/* Draw nodes */}
            {nodes.map((node) => (
              <TreeNode
                key={node.id}
                node={node}
                isExpanded={expandedNodes.has(node.id)}
                onToggle={() => toggleNode(node.id)}
                onClick={() => onNodeClick?.(node.data)}
                onReferenceClick={() => onReferenceClick?.(node.data)}
              />
            ))}
          </g>
        </svg>
      </div>
    </div>
  );
});

/**
 * Individual tree node component
 */
const TreeNode = memo(({ node, isExpanded, onToggle, onClick, onReferenceClick }) => {
  const { x, y, data, hasChildren } = node;
  
  // Determine colors
  let fillColor = "#334155"; // slate-700
  let strokeColor = "#475569"; // slate-600
  let textColor = "#f1f5f9"; // slate-100
  
  if (data.isError) {
    fillColor = "#b91c1c"; // red-700
    strokeColor = "#ef4444"; // red-500
  } else if (data.isReference) {
    fillColor = "#0e7490"; // cyan-700
    strokeColor = "#06b6d4"; // cyan-500
  }

  // Build label
  let label = data.type;
  if (data.name) label = `${data.type}: ${data.name}`;
  if (label.length > 25) label = label.slice(0, 22) + '...';

  const nodeWidth = 180;
  const nodeHeight = 50;

  const handleClick = (e) => {
    e.stopPropagation();
    if (data.isReference && data.targetFile) {
      onReferenceClick();
    } else {
      onClick();
    }
  };

  return (
    <g transform={`translate(${x - nodeWidth/2}, ${y})`}>
      {/* Main rectangle */}
      <rect
        width={nodeWidth}
        height={nodeHeight}
        rx="6"
        fill={fillColor}
        stroke={strokeColor}
        strokeWidth="2"
        className="cursor-pointer hover:brightness-110 transition-all"
        onClick={handleClick}
      />

      {/* Type label */}
      <text
        x={nodeWidth / 2}
        y={18}
        textAnchor="middle"
        fill={textColor}
        fontSize="11"
        fontWeight="600"
        className="pointer-events-none select-none"
      >
        {label}
      </text>

      {/* Line number */}
      {data.loc && (
        <text
          x={nodeWidth / 2}
          y={34}
          textAnchor="middle"
          fill="#94a3b8"
          fontSize="10"
          className="pointer-events-none select-none"
        >
          Line {data.loc.start.line}
          {data.loc.end.line !== data.loc.start.line && `-${data.loc.end.line}`}
        </text>
      )}

      {/* Reference indicator */}
      {data.isReference && (
        <g>
          <circle cx={nodeWidth - 12} cy={12} r="8" fill="#06b6d4" />
          <text x={nodeWidth - 12} y={16} textAnchor="middle" fill="white" fontSize="10">→</text>
        </g>
      )}

      {/* Expand/collapse button */}
      {hasChildren && (
        <g
          transform={`translate(${nodeWidth / 2 - 10}, ${nodeHeight - 5})`}
          onClick={(e) => { e.stopPropagation(); onToggle(); }}
          className="cursor-pointer"
        >
          <circle r="10" fill="#1e293b" stroke="#475569" strokeWidth="1.5" />
          <text
            y="4"
            textAnchor="middle"
            fill="white"
            fontSize="14"
            fontWeight="bold"
          >
            {isExpanded ? '−' : '+'}
          </text>
        </g>
      )}
    </g>
  );
});

/**
 * Calculate tree layout positions
 */
function layoutTree(tree, expandedNodes) {
  const nodes = [];
  const edges = [];
  const NODE_WIDTH = 180;
  const NODE_HEIGHT = 50;
  const H_SPACING = 30;
  const V_SPACING = 80;

  // Calculate subtree widths
  function calcWidth(node, nodeId) {
    if (!node) return 0;
    if (!expandedNodes.has(nodeId) || !node.children?.length) {
      return NODE_WIDTH;
    }
    let totalWidth = 0;
    node.children.forEach((child, i) => {
      totalWidth += calcWidth(child, `${nodeId}-${i}`);
      if (i < node.children.length - 1) totalWidth += H_SPACING;
    });
    return Math.max(NODE_WIDTH, totalWidth);
  }

  // Position nodes
  function position(node, nodeId, x, y, parentX = null, parentY = null) {
    if (!node) return;

    const treeWidth = calcWidth(node, nodeId);
    const nodeX = x + treeWidth / 2;

    nodes.push({
      id: nodeId,
      x: nodeX,
      y,
      data: node,
      hasChildren: node.children?.length > 0
    });

    if (parentX !== null && parentY !== null) {
      edges.push({
        x1: parentX,
        y1: parentY + NODE_HEIGHT,
        x2: nodeX,
        y2: y
      });
    }

    if (expandedNodes.has(nodeId) && node.children?.length) {
      let childX = x;
      node.children.forEach((child, i) => {
        const childId = `${nodeId}-${i}`;
        const childWidth = calcWidth(child, childId);
        position(child, childId, childX, y + NODE_HEIGHT + V_SPACING, nodeX, y);
        childX += childWidth + H_SPACING;
      });
    }
  }

  position(tree, 'root', 0, 0);

  // Calculate bounds
  let maxX = 0, maxY = 0;
  nodes.forEach(n => {
    maxX = Math.max(maxX, n.x + NODE_WIDTH);
    maxY = Math.max(maxY, n.y + NODE_HEIGHT);
  });

  return { nodes, edges, width: maxX + 100, height: maxY + 100 };
}

export default TreeVisualization;
