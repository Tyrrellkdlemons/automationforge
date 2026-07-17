import {
  json,
  loadCredentials,
  verifyPassword,
  signToken,
  sessionCookie,
  credentialsCookie,
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
    const { username, password } = parseBody(event);
    if (!username || !password) {
      return json(400, { error: "Username and password required" });
    }

    const creds = loadCredentials(event);
    if (
      username !== creds.username ||
      !verifyPassword(password, creds.passwordHash)
    ) {
      return json(401, { error: "Invalid username or password" });
    }

    const token = signToken({
      sub: creds.username,
      mustChangePassword: !!creds.mustChangePassword,
    });

    const cookieBits = multiCookieHeaders(
      sessionCookie(token),
      credentialsCookie(creds)
    );

    return {
      statusCode: 200,
      ...cookieBits,
      body: JSON.stringify({
        ok: true,
        username: creds.username,
        mustChangePassword: !!creds.mustChangePassword,
      }),
    };
  } catch (err) {
    console.error("login error", err);
    return json(500, { error: err.message || "Login failed" });
  }
}
