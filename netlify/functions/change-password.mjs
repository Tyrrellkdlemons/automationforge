import {
  json,
  loadCredentials,
  saveCredentials,
  hashPassword,
  signToken,
  sessionCookie,
  clearSessionCookie,
  readSession,
  parseBody,
} from "./_shared.mjs";

export async function handler(event) {
  if (event.httpMethod === "OPTIONS") {
    return json(204, {});
  }
  if (event.httpMethod !== "POST") {
    return json(405, { error: "Method not allowed" });
  }

  try {
    const session = readSession(event);
    if (!session) {
      return json(401, { error: "Not authenticated" });
    }

    const { newPassword, confirmPassword } = parseBody(event);
    if (!newPassword || newPassword.length < 8) {
      return json(400, { error: "Password must be at least 8 characters" });
    }
    if (newPassword !== confirmPassword) {
      return json(400, { error: "Passwords do not match" });
    }
    if (newPassword === "admin") {
      return json(400, { error: "Choose a password other than the default" });
    }

    const creds = await loadCredentials();
    creds.passwordHash = hashPassword(newPassword);
    creds.mustChangePassword = false;
    creds.updatedAt = new Date().toISOString();
    await saveCredentials(creds);

    const token = signToken({
      sub: creds.username,
      mustChangePassword: false,
    });

    return json(
      200,
      { ok: true, mustChangePassword: false },
      { "Set-Cookie": sessionCookie(token) }
    );
  } catch (err) {
    return json(500, { error: err.message || "Password change failed" });
  }
}

export { clearSessionCookie };
