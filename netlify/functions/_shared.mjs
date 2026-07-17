import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { parse as parseCookie, serialize as serializeCookie } from "cookie";

const COOKIE_NAME = "af_session";
const CREDS_COOKIE = "af_creds";
const DEFAULT_USER = "admin";
const DEFAULT_PASS = "admin";

export function json(statusCode, body, extraHeaders = {}) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
    body: JSON.stringify(body),
  };
}

export function getSecret() {
  return process.env.AUTH_SECRET || "automationforge-dev-secret-change-me";
}

function defaultCreds() {
  return {
    username: DEFAULT_USER,
    passwordHash: bcrypt.hashSync(DEFAULT_PASS, 10),
    mustChangePassword: true,
    updatedAt: null,
  };
}

/** Persist credentials in a signed httpOnly cookie (works without Netlify Blobs). */
export function loadCredentials(event) {
  const header = event.headers.cookie || event.headers.Cookie || "";
  const cookies = parseCookie(header);
  const raw = cookies[CREDS_COOKIE];
  if (raw) {
    try {
      const payload = jwt.verify(raw, getSecret());
      if (payload?.passwordHash && payload?.username) {
        return {
          username: payload.username,
          passwordHash: payload.passwordHash,
          mustChangePassword: !!payload.mustChangePassword,
          updatedAt: payload.updatedAt || null,
        };
      }
    } catch {
      // fall through to defaults
    }
  }
  return defaultCreds();
}

export function credentialsCookie(creds) {
  const token = jwt.sign(
    {
      username: creds.username,
      passwordHash: creds.passwordHash,
      mustChangePassword: !!creds.mustChangePassword,
      updatedAt: creds.updatedAt || null,
    },
    getSecret(),
    { expiresIn: "365d" }
  );
  return serializeCookie(CREDS_COOKIE, token, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
}

export function verifyPassword(plain, hash) {
  return bcrypt.compareSync(plain, hash);
}

export function hashPassword(plain) {
  return bcrypt.hashSync(plain, 10);
}

export function signToken(payload) {
  return jwt.sign(payload, getSecret(), { expiresIn: "7d" });
}

export function verifyToken(token) {
  try {
    return jwt.verify(token, getSecret());
  } catch {
    return null;
  }
}

export function readSession(event) {
  const header = event.headers.cookie || event.headers.Cookie || "";
  const cookies = parseCookie(header);
  const token = cookies[COOKIE_NAME];
  if (!token) return null;
  return verifyToken(token);
}

export function sessionCookie(token) {
  return serializeCookie(COOKIE_NAME, token, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
}

export function clearSessionCookie() {
  return serializeCookie(COOKIE_NAME, "", {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}

export function parseBody(event) {
  if (!event.body) return {};
  try {
    const raw = event.isBase64Encoded
      ? Buffer.from(event.body, "base64").toString("utf8")
      : event.body;
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

/** Join multiple Set-Cookie headers for Netlify/AWS style responses. */
export function multiCookieHeaders(...cookies) {
  // Netlify supports multiValueHeaders for multiple Set-Cookie
  return {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    multiValueHeaders: { "Set-Cookie": cookies.filter(Boolean) },
  };
}
