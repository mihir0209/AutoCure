export function astToSemanticTree(node) {
  if (!node || typeof node !== "object") return null;

  let label = node.type;

  if (node.type === "FunctionDeclaration") {
    label = `Function: ${node.id?.name ?? "anonymous"}`;
  } else if (node.type === "Identifier") {
    label = `Identifier: ${node.name}`;
  } else if (node.type === "VariableDeclarator") {
    label = `Variable: ${node.id?.name}`;
  } else if (node.type === "BinaryExpression") {
    label = `Expression (${node.operator})`;
  } else if (node.type === "LogicalExpression") {
    label = `Logical (${node.operator})`;
  } else if (node.type === "ReturnStatement") {
    label = "Return";
  } else if (node.type === "IfStatement") {
    label = "If condition";
  } else if (node.type === "NumericLiteral") {
    label = `Literal: ${node.value}`;
  } else if (node.type === "NullLiteral") {
    label = "Literal: null";
  }

  const children = [];

  for (const key in node) {
    const value = node[key];
    if (Array.isArray(value)) {
      value.forEach(v => v?.type && children.push(astToSemanticTree(v)));
    } else if (value?.type) {
      children.push(astToSemanticTree(value));
    }
  }

  return {
    name: label, // 🔥 THIS is what react-d3-tree renders
    attributes: node.loc ? { line: node.loc.start.line } : undefined,
    children
  };
}
