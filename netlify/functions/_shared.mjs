import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import { parse as parseCookie, serialize as serializeCookie } from "cookie";
import { getStore } from "@netlify/blobs";

const COOKIE_NAME = "af_session";
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

function authStore() {
  return getStore({ name: "automationforge-auth", consistency: "strong" });
}

export async function loadCredentials() {
  const store = authStore();
  let creds = await store.get("credentials", { type: "json" });
  if (!creds) {
    creds = {
      username: DEFAULT_USER,
      passwordHash: bcrypt.hashSync(DEFAULT_PASS, 10),
      mustChangePassword: true,
      updatedAt: null,
    };
    await store.setJSON("credentials", creds);
  }
  return creds;
}

export async function saveCredentials(creds) {
  const store = authStore();
  await store.setJSON("credentials", creds);
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
