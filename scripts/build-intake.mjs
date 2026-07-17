/**
 * Ensure intake site is publish-ready and mirror source into public/submit.html
 * for documentation / local previews.
 */
import { cpSync, mkdirSync, writeFileSync, readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "sites", "intake");
const publicDir = join(root, "public");

mkdirSync(publicDir, { recursive: true });
cpSync(join(src, "index.html"), join(publicDir, "submit.html"));
cpSync(join(src, "styles.css"), join(publicDir, "styles.css"));
cpSync(join(src, "favicon.svg"), join(publicDir, "favicon.svg"));

writeFileSync(
  join(src, "_headers"),
  `/*
  X-Robots-Tag: noindex, nofollow
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=()
`
);

// Soft-check: intake should not leak operator internals
const html = readFileSync(join(src, "index.html"), "utf8");
for (const banned of ["Firebase", "Firestore", "AutomationForge", "worker.py", "8XX", "saas_trial"]) {
  if (html.includes(banned)) {
    console.warn(`build-intake warning: found internal term "${banned}" in public HTML`);
  }
}

console.log("build-intake: sites/intake ready; public/ mirrored");
