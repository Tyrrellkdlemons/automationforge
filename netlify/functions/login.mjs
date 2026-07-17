import {
  json,
  loadCredentials,
  verifyPassword,
  signToken,
  sessionCookie,
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
    const { username, password } = parseBody(event);
    if (!username || !password) {
      return json(400, { error: "Username and password required" });
    }

    const creds = await loadCredentials();
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

    return json(
      200,
      {
        ok: true,
        username: creds.username,
        mustChangePassword: !!creds.mustChangePassword,
      },
      { "Set-Cookie": sessionCookie(token) }
    );
  } catch (err) {
    return json(500, { error: err.message || "Login failed" });
  }
}
