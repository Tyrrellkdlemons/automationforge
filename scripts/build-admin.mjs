/**
 * Build AutomationForge command-center site into sites/admin (already source)
 * and sync a copy into legacy web/ for older deploy configs.
 */
import { cpSync, mkdirSync, rmSync, existsSync, writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "sites", "admin");
const legacy = join(root, "web");

mkdirSync(legacy, { recursive: true });
for (const name of ["index.html", "app.js", "styles.css", "favicon.svg", "_redirects"]) {
  const from = join(src, name);
  if (existsSync(from)) cpSync(from, join(legacy, name));
}
// Admin site must NOT ship the public form
const submit = join(legacy, "submit.html");
if (existsSync(submit)) rmSync(submit);

writeFileSync(
  join(legacy, "_headers"),
  `/*
  X-Robots-Tag: noindex, nofollow
  Referrer-Policy: same-origin
`
);

console.log("build-admin: sites/admin ready; legacy web/ synced (no submit.html)");
