import React, { useState, useCallback, memo, useRef, useEffect } from "react";

/**
 * TreeVisualization - Renders AST as an interactive tree graph
 * Uses SVG for proper tree visualization with lines
 * @param {object} tree - Tree data structure
 * @param {function} onNodeClick - Callback when node is clicked
 * @param {function} onReferenceClick - Callback when reference node is clicked
 * @param {string} focusedNodeId - Node ID to focus/highlight (for code→tree navigation)
 */
const TreeVisualization = memo(({ tree, onNodeClick, onReferenceClick, focusedNodeId }) => {
  const [expandedNodes, setExpandedNodes] = useState(new Set(['root']));
  const [transform, setTransform] = useState({ x: 50, y: 20, scale: 1 });
  const [showMinimap, setShowMinimap] = useState(true);
  const containerRef = useRef(null);
  const isDragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });
  const minimapDragging = useRef(false);

  // Initialize with first level expanded
  useEffect(() => {
    if (tree) {
      const initial = new Set(['root']);
      if (tree.children) {
        tree.children.forEach((_, i) => initial.add(`root-${i}`));
      }
      setExpandedNodes(initial);
      // Reset transform when tree changes
      setTransform({ x: 50, y: 20, scale: 1 });
    }
  }, [tree]);

  // Auto-navigate to focused node (code→tree navigation)
  useEffect(() => {
    if (focusedNodeId && tree) {
      // Expand path to focused node
      const pathIds = focusedNodeId.split('-');
      const newExpanded = new Set(expandedNodes);
      let currentPath = pathIds[0];
      newExpanded.add(currentPath);
      for (let i = 1; i < pathIds.length; i++) {
        currentPath += `-${pathIds[i]}`;
        newExpanded.add(currentPath);
      }
      setExpandedNodes(newExpanded);

      // Calculate the position of the focused node and center on it
      setTimeout(() => {
        const { nodes } = layoutTree(tree, newExpanded);
        const focusedNode = nodes.find(n => n.id === focusedNodeId);
        if (focusedNode && containerRef.current) {
          const rect = containerRef.current.getBoundingClientRect();
          const centerX = rect.width / 2;
          const centerY = rect.height / 2;
          setTransform(prev => ({
            ...prev,
            x: centerX - focusedNode.x * prev.scale,
            y: centerY - focusedNode.y * prev.scale
          }));
        }
      }, 50);
    }
  }, [focusedNodeId, tree]);

  // Prevent page scroll when cursor is inside the canvas
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const preventScroll = (e) => {
      e.preventDefault();
      e.stopPropagation();
      
      // Handle zoom
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      setTransform(prev => ({
        ...prev,
        scale: Math.max(0.2, Math.min(3, prev.scale * delta))
      }));
    };

    // Use passive: false to allow preventDefault
    container.addEventListener('wheel', preventScroll, { passive: false });
    
    return () => {
      container.removeEventListener('wheel', preventScroll);
    };
  }, []);

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
    // Allow dragging from anywhere in the canvas
    isDragging.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
    e.preventDefault();
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

  // Minimap click to navigate
  const handleMinimapClick = useCallback((e) => {
    if (!containerRef.current) return;
    const minimapRect = e.currentTarget.getBoundingClientRect();
    const container = containerRef.current.getBoundingClientRect();
    
    // Calculate layout dimensions
    const { width: treeWidth, height: treeHeight } = layoutTree(tree, expandedNodes);
    const minimapWidth = 180;
    const minimapHeight = 120;
    const padding = 10;
    
    // Scale factor for minimap
    const scaleX = (minimapWidth - 2 * padding) / Math.max(treeWidth, 1);
    const scaleY = (minimapHeight - 2 * padding) / Math.max(treeHeight, 1);
    const minimapScale = Math.min(scaleX, scaleY);
    
    // Get click position relative to minimap
    const clickX = (e.clientX - minimapRect.left - padding) / minimapScale;
    const clickY = (e.clientY - minimapRect.top - padding) / minimapScale;
    
    // Center viewport on clicked position
    setTransform(prev => ({
      ...prev,
      x: container.width / 2 - clickX * prev.scale,
      y: container.height / 2 - clickY * prev.scale
    }));
  }, [tree, expandedNodes]);

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
    <div className="h-full flex flex-col bg-slate-900 relative">
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
        <button
          onClick={() => setShowMinimap(prev => !prev)}
          className={`px-3 py-1 rounded text-xs ${showMinimap ? 'bg-cyan-700 hover:bg-cyan-600' : 'bg-slate-700 hover:bg-slate-600'}`}
        >
          {showMinimap ? '🗺️ Minimap' : '🗺️'}
        </button>
        <span className="text-slate-500 text-xs ml-auto">
          Drag to pan • Scroll to zoom • Click nodes to view code
        </span>
      </div>

      {/* SVG Canvas - fixed viewport, no page scroll */}
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden cursor-grab active:cursor-grabbing select-none"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ touchAction: 'none' }}
      >
        <svg
          width="100%"
          height="100%"
          style={{ minWidth: '100%', minHeight: '100%', display: 'block' }}
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
                isFocused={node.id === focusedNodeId}
                onToggle={() => toggleNode(node.id)}
                onClick={() => onNodeClick?.(node.data)}
                onReferenceClick={() => onReferenceClick?.(node.data)}
              />
            ))}
          </g>
        </svg>
      </div>

      {/* Minimap overlay */}
      {showMinimap && (
        <Minimap
          nodes={nodes}
          edges={edges}
          width={width}
          height={height}
          transform={transform}
          containerRef={containerRef}
          onClick={handleMinimapClick}
          focusedNodeId={focusedNodeId}
        />
      )}
    </div>
  );
});

/**
 * Minimap component for quick navigation
 */
const Minimap = memo(({ nodes, edges, width, height, transform, containerRef, onClick, focusedNodeId }) => {
  const minimapWidth = 180;
  const minimapHeight = 120;
  const padding = 10;

  // Scale factor
  const scaleX = (minimapWidth - 2 * padding) / Math.max(width, 1);
  const scaleY = (minimapHeight - 2 * padding) / Math.max(height, 1);
  const minimapScale = Math.min(scaleX, scaleY);

  // Calculate viewport rectangle
  let viewportRect = null;
  if (containerRef.current) {
    const container = containerRef.current.getBoundingClientRect();
    const viewportX = (-transform.x / transform.scale);
    const viewportY = (-transform.y / transform.scale);
    const viewportW = container.width / transform.scale;
    const viewportH = container.height / transform.scale;
    
    viewportRect = {
      x: padding + viewportX * minimapScale,
      y: padding + viewportY * minimapScale,
      w: viewportW * minimapScale,
      h: viewportH * minimapScale
    };
  }

  return (
    <div 
      className="absolute bottom-4 right-4 bg-slate-800/90 border border-slate-600 rounded-lg shadow-lg cursor-pointer"
      style={{ width: minimapWidth, height: minimapHeight }}
      onClick={onClick}
      title="Click to navigate"
    >
      {/* Header */}
      <div className="absolute top-1 left-2 text-xs text-slate-400 pointer-events-none">🗺️</div>
      
      <svg width={minimapWidth} height={minimapHeight}>
        <g transform={`translate(${padding}, ${padding}) scale(${minimapScale})`}>
          {/* Edges */}
          {edges.map((edge, i) => (
            <line
              key={`mm-edge-${i}`}
              x1={edge.x1}
              y1={edge.y1 + 25}
              x2={edge.x2}
              y2={edge.y2}
              stroke="#475569"
              strokeWidth={1 / minimapScale}
            />
          ))}
          
          {/* Nodes as dots */}
          {nodes.map((node) => (
            <rect
              key={`mm-${node.id}`}
              x={node.x - 5}
              y={node.y}
              width={10}
              height={5}
              rx={2}
              fill={node.id === focusedNodeId ? '#06b6d4' : node.data.isError ? '#ef4444' : node.data.isReference ? '#0891b2' : '#64748b'}
            />
          ))}
        </g>
        
        {/* Viewport rectangle */}
        {viewportRect && (
          <rect
            x={Math.max(0, viewportRect.x)}
            y={Math.max(0, viewportRect.y)}
            width={Math.min(viewportRect.w, minimapWidth - Math.max(0, viewportRect.x))}
            height={Math.min(viewportRect.h, minimapHeight - Math.max(0, viewportRect.y))}
            fill="rgba(96, 165, 250, 0.2)"
            stroke="#60a5fa"
            strokeWidth="1.5"
            strokeDasharray="4,2"
          />
        )}
      </svg>
    </div>
  );
});

/**
 * Individual tree node component
 */
const TreeNode = memo(({ node, isExpanded, isFocused, onToggle, onClick, onReferenceClick }) => {
  const { x, y, data, hasChildren } = node;
  
  // Determine colors
  let fillColor = "#334155"; // slate-700
  let strokeColor = "#475569"; // slate-600
  let textColor = "#f1f5f9"; // slate-100
  
  if (isFocused) {
    fillColor = "#0e7490"; // cyan-700
    strokeColor = "#22d3ee"; // cyan-400
  } else if (data.isError) {
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
