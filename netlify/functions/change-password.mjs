import {
  json,
  loadCredentials,
  hashPassword,
  signToken,
  sessionCookie,
  credentialsCookie,
  readSession,
  parseBody,
  multiCookieHeaders,
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

    const creds = loadCredentials(event);
    creds.passwordHash = hashPassword(newPassword);
    creds.mustChangePassword = false;
    creds.updatedAt = new Date().toISOString();

    const token = signToken({
      sub: creds.username,
      mustChangePassword: false,
    });

    const cookieBits = multiCookieHeaders(
      sessionCookie(token),
      credentialsCookie(creds)
    );

    return {
      statusCode: 200,
      ...cookieBits,
      body: JSON.stringify({ ok: true, mustChangePassword: false }),
    };
  } catch (err) {
    console.error("change-password error", err);
    return json(500, { error: err.message || "Password change failed" });
  }
}
