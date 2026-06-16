// Minimal DOM helpers shared by the config menu. Building nodes
// programmatically (rather than innerHTML) keeps user-typed values out of
// the HTML parser - no escaping, no injection.

/**
 * Create an element. `props` are assigned as properties when they exist on
 * the node (value, checked, type, className, textContent, min, …) and as
 * attributes otherwise. `children` may be a node, a string, an array, or
 * null entries (skipped).
 */
export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === 'className') node.className = value;
    else if (key === 'textContent') node.textContent = value;
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child != null) node.append(child);
  }
  return node;
}

/** Remove every child of a node. */
export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}
