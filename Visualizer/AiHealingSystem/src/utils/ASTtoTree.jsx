export function astToTree(node, highlightSet = new Set()) {
  if (!node) return null;

  const key = node.loc
    ? `${node.type}:${node.loc.start.line}-${node.loc.end.line}`
    : node.type;

  return {
    name: node.name
      ? `${node.type} (${node.name})`
      : node.type,
    highlight: highlightSet.has(key),
    attributes: node.loc
      ? {
          line: `${node.loc.start.line}-${node.loc.end.line}`
        }
      : {},
    children: node.children
      ? node.children.map(child => astToTree(child, highlightSet))
      : []
  };
}
