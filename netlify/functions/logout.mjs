import { json, clearSessionCookie } from "./_shared.mjs";

export async function handler(event) {
  if (event.httpMethod === "OPTIONS") {
    return json(204, {});
  }
  if (event.httpMethod !== "POST") {
    return json(405, { error: "Method not allowed" });
  }

  return json(200, { ok: true }, { "Set-Cookie": clearSessionCookie() });
}
