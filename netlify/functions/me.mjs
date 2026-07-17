import { json, readSession, loadCredentials } from "./_shared.mjs";

export async function handler(event) {
  if (event.httpMethod === "OPTIONS") {
    return json(204, {});
  }
  if (event.httpMethod !== "GET") {
    return json(405, { error: "Method not allowed" });
  }

  try {
    const session = readSession(event);
    if (!session) {
      return json(401, { authenticated: false });
    }

    const creds = await loadCredentials();
    return json(200, {
      authenticated: true,
      username: session.sub || creds.username,
      mustChangePassword: !!creds.mustChangePassword,
    });
  } catch (err) {
    return json(500, { error: err.message || "Session check failed" });
  }
}
