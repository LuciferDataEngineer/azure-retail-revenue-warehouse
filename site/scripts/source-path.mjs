import { existsSync } from "node:fs";
import { join } from "node:path";

export function sourcePath(root, name) {
  if (!existsSync(join(root, "templates/protected-runtime.json"))) return join(root, name);
  if (name.startsWith("src/") || name.startsWith("docs/")) return join(root, name);
  if (name.startsWith("scripts/")) return join(root, "scripts/template", name.slice(8));
  return join(root, "templates", name);
}
