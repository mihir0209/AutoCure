export function simplifyAst(node) {
  if (!node || typeof node !== "object") return null;

  const result = {
    type: node.type
  };

  if (node.id?.name) result.name = node.id.name;
  if (node.key?.name) result.name = node.key.name;
  if (node.loc) result.loc = node.loc;

  const children = [];

  for (const key in node) {
    const value = node[key];

    if (Array.isArray(value)) {
      value.forEach(v => {
        if (v?.type) children.push(simplifyAst(v));
      });
    } else if (value?.type) {
      children.push(simplifyAst(value));
    }
  }

  if (children.length) result.children = children;

  return result;
}
