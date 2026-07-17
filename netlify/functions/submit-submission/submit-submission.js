/**
 * Netlify Function: create a Firestore submission from the public form.
 *
 * Auth: require header `x-submission-secret` matching env SUBMISSION_SECRET.
 * Credentials: FIREBASE_SERVICE_ACCOUNT_JSON (stringified service account).
 */
const admin = require("firebase-admin");

let initTried = false;

function json(statusCode, body) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type, x-submission-secret",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Cache-Control": "no-store",
    },
    body: JSON.stringify(body),
  };
}

function initFirebase() {
  if (admin.apps.length) return;
  if (initTried) return;
  initTried = true;

  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
  if (!raw) {
    throw new Error("FIREBASE_SERVICE_ACCOUNT_JSON is not set");
  }
  const sa = typeof raw === "string" ? JSON.parse(raw) : raw;
  admin.initializeApp({
    credential: admin.credential.cert(sa),
  });
}

function parseBody(event) {
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

function isValidDob(dob) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dob || "")) return false;
  const d = new Date(dob + "T00:00:00Z");
  return !Number.isNaN(d.getTime());
}

exports.handler = async function handler(event) {
  if (event.httpMethod === "OPTIONS") {
    return json(204, {});
  }
  if (event.httpMethod !== "POST") {
    return json(405, { error: "Method not allowed" });
  }

  try {
    const expected = process.env.SUBMISSION_SECRET || "";
    const provided =
      event.headers["x-submission-secret"] ||
      event.headers["X-Submission-Secret"] ||
      "";
    if (!expected || provided !== expected) {
      return json(401, { error: "Unauthorized" });
    }

    const body = parseBody(event);
    const firstName = String(body.firstName || "").trim();
    const lastName = String(body.lastName || "").trim();
    const email = String(body.email || "").trim().toLowerCase();
    const dob = String(body.dob || body.dateOfBirth || "").trim();
    const addressRaw = body.address;

    if (!firstName || !lastName) {
      return json(400, { error: "First name and last name are required" });
    }
    if (!email || !email.includes("@")) {
      return json(400, { error: "A valid email is required" });
    }
    if (!isValidDob(dob)) {
      return json(400, { error: "Date of birth must be YYYY-MM-DD" });
    }

    let address = null;
    if (typeof addressRaw === "string" && addressRaw.trim()) {
      address = { street: addressRaw.trim(), city: "", state: "", zip: "", country: "United States" };
    } else if (addressRaw && typeof addressRaw === "object") {
      address = {
        street: String(addressRaw.street || "").trim(),
        city: String(addressRaw.city || "").trim(),
        state: String(addressRaw.state || "").trim(),
        zip: String(addressRaw.zip || addressRaw.postal || "").trim(),
        country: String(addressRaw.country || "United States").trim(),
      };
      if (!address.street && !address.city) address = null;
    }

    initFirebase();
    const db = admin.firestore();
    const now = new Date().toISOString();
    const doc = {
      firstName,
      lastName,
      email,
      dob,
      address,
      status: "new",
      issued_id: null,
      flows: {
        newsletter: { status: "pending", error: null },
        saas_trial: { status: "pending", error: null },
        job_profile: { status: "pending", error: null },
      },
      manualOverride: false,
      manualLogs: [],
      createdAt: now,
      updatedAt: now,
    };

    const ref = await db.collection("submissions").add(doc);
    return json(200, {
      ok: true,
      submissionId: ref.id,
      message: "Submission received. You will receive your unique ID by email after processing.",
    });
  } catch (err) {
    console.error("submit-submission error", err);
    return json(500, { error: err.message || "Server error" });
  }
};
