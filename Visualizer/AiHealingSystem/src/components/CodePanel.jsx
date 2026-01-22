import React, { useEffect, useRef, memo, useCallback } from "react";

/**
 * CodePanel - Displays file content with syntax highlighting and line highlighting
 * @param {string} content - File content to display
 * @param {number} highlightLine - Currently highlighted line (from tree node)
 * @param {string} filename - Name of the file
 * @param {function} onLineClick - Callback when a line is clicked (for code→tree navigation)
 * @param {object} nodesByLine - Map of line numbers to tree nodes for code→tree navigation
 */
const CodePanel = memo(({ content, highlightLine, filename, onLineClick, nodesByLine }) => {
  const containerRef = useRef(null);
  const highlightRef = useRef(null);

  // Auto-scroll to highlighted line
  useEffect(() => {
    if (highlightLine && highlightRef.current) {
      highlightRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
    }
  }, [highlightLine]);

  // Handle line click - find nodes at this line and trigger navigation
  const handleLineClick = useCallback((lineNum) => {
    if (onLineClick && nodesByLine) {
      // Find node at this line
      const nodesAtLine = nodesByLine[lineNum];
      if (nodesAtLine && nodesAtLine.length > 0) {
        // Prefer the most specific (deepest) node at this line
        const targetNode = nodesAtLine[nodesAtLine.length - 1];
        onLineClick(targetNode);
      }
    }
  }, [onLineClick, nodesByLine]);

  if (!content) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500">
        <p>No content to display</p>
      </div>
    );
  }

  const lines = content.split('\n');

  return (
    <div className="h-full flex flex-col bg-slate-900">
      {/* Header */}
      <div className="px-4 py-2 bg-slate-800 border-b border-slate-700 flex items-center gap-2 shrink-0">
        <span className="text-sm text-slate-300 font-mono">📝 {filename}</span>
        {highlightLine && (
          <span className="text-xs bg-blue-600 px-2 py-0.5 rounded">Line {highlightLine}</span>
        )}
        <span className="text-xs text-slate-500 ml-auto">{lines.length} lines</span>
        {onLineClick && (
          <span className="text-xs text-slate-500">Click line to navigate to tree</span>
        )}
      </div>

      {/* Code content */}
      <div ref={containerRef} className="flex-1 overflow-auto font-mono text-sm">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, index) => {
              const lineNum = index + 1;
              const isHighlighted = lineNum === highlightLine;
              const hasNode = nodesByLine && nodesByLine[lineNum] && nodesByLine[lineNum].length > 0;
              
              return (
                <tr
                  key={lineNum}
                  ref={isHighlighted ? highlightRef : null}
                  onClick={() => handleLineClick(lineNum)}
                  className={`
                    ${isHighlighted ? 'bg-yellow-500/20' : 'hover:bg-slate-800/50'}
                    ${hasNode && onLineClick ? 'cursor-pointer' : ''}
                  `}
                  title={hasNode ? `Click to navigate to: ${nodesByLine[lineNum].map(n => n.type).join(' > ')}` : ''}
                >
                  {/* Line number */}
                  <td className={`px-3 py-0.5 text-right select-none border-r border-slate-700 w-12 shrink-0 ${
                    isHighlighted ? 'text-yellow-400 bg-yellow-500/10' : hasNode ? 'text-blue-400' : 'text-slate-600'
                  }`}>
                    {hasNode && <span className="text-xs mr-1">●</span>}
                    {lineNum}
                  </td>
                  {/* Code */}
                  <td className={`px-4 py-0.5 whitespace-pre ${
                    isHighlighted ? 'text-yellow-100' : 'text-slate-300'
                  }`}>
                    <SyntaxHighlight code={line} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
});

/**
 * Basic syntax highlighting for JS/TS
 */
function SyntaxHighlight({ code }) {
  if (!code) return <span>&nbsp;</span>;

  // Simple regex-based highlighting
  const patterns = [
    // Comments
    { regex: /(\/\/.*$)/gm, className: 'text-slate-500' },
    // Strings
    { regex: /(['"`])((?:\\.|(?!\1)[^\\])*?)\1/g, className: 'text-green-400' },
    // Keywords
    { regex: /\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|try|catch|finally|throw|new|class|extends|import|export|from|default|async|await|typeof|instanceof|in|of|this|super|static|get|set)\b/g, className: 'text-purple-400' },
    // Built-in objects
    { regex: /\b(console|document|window|Array|Object|String|Number|Boolean|Promise|Map|Set|JSON|Math)\b/g, className: 'text-cyan-400' },
    // Numbers
    { regex: /\b(\d+\.?\d*)\b/g, className: 'text-amber-400' },
    // Functions
    { regex: /\b([a-zA-Z_$][\w$]*)\s*(?=\()/g, className: 'text-yellow-300' },
    // Arrow functions
    { regex: /(=>)/g, className: 'text-purple-400' },
    // Operators
    { regex: /([+\-*/%=<>!&|^~?:]+)/g, className: 'text-slate-400' },
  ];

  // Build highlighted segments
  let result = code;
  const segments = [];
  let lastIndex = 0;

  // Create a combined regex for basic tokenization
  const combinedPattern = /(['"`])((?:\\.|(?!\1)[^\\])*?)\1|\/\/.*$|\b(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|try|catch|finally|throw|new|class|extends|import|export|from|default|async|await|typeof|instanceof|in|of|this|super|static|get|set)\b|\b(console|document|window|Array|Object|String|Number|Boolean|Promise|Map|Set|JSON|Math)\b|\b(\d+\.?\d*)\b/gm;

  let match;
  while ((match = combinedPattern.exec(code)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      segments.push({
        text: code.slice(lastIndex, match.index),
        className: ''
      });
    }

    // Determine type
    let className = 'text-slate-300';
    const matched = match[0];
    
    if (matched.startsWith('//')) {
      className = 'text-slate-500';
    } else if (matched.startsWith('"') || matched.startsWith("'") || matched.startsWith('`')) {
      className = 'text-green-400';
    } else if (/^(const|let|var|function|return|if|else|for|while|do|switch|case|break|continue|try|catch|finally|throw|new|class|extends|import|export|from|default|async|await|typeof|instanceof|in|of|this|super|static|get|set)$/.test(matched)) {
      className = 'text-purple-400';
    } else if (/^(console|document|window|Array|Object|String|Number|Boolean|Promise|Map|Set|JSON|Math)$/.test(matched)) {
      className = 'text-cyan-400';
    } else if (/^\d+\.?\d*$/.test(matched)) {
      className = 'text-amber-400';
    }

    segments.push({
      text: matched,
      className
    });

    lastIndex = match.index + matched.length;
  }

  // Add remaining text
  if (lastIndex < code.length) {
    segments.push({
      text: code.slice(lastIndex),
      className: ''
    });
  }

  if (segments.length === 0) {
    return <span>{code}</span>;
  }

  return (
    <>
      {segments.map((seg, i) => (
        <span key={i} className={seg.className}>{seg.text}</span>
      ))}
    </>
  );
}

export default CodePanel;
