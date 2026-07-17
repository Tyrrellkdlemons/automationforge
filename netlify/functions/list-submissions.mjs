import { createRequire } from "module";
import { json, readSession } from "./_shared.mjs";

const require = createRequire(import.meta.url);
const admin = require("firebase-admin");

function initFirebase() {
  if (admin.apps.length) return;
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
  if (!raw) throw new Error("FIREBASE_SERVICE_ACCOUNT_JSON is not set");
  let cred;
  try {
    cred = JSON.parse(raw);
  } catch {
    throw new Error("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON");
  }
  if (typeof cred.private_key === "string") {
    cred.private_key = cred.private_key.replace(/\\n/g, "\n");
  }
  admin.initializeApp({ credential: admin.credential.cert(cred) });
}

export async function handler(event) {
  if (event.httpMethod === "OPTIONS") {
    return json(204, {}, {
      "Access-Control-Allow-Origin": event.headers.origin || "*",
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
    });
  }
  if (event.httpMethod !== "GET") return json(405, { error: "Method not allowed" });

  const session = readSession(event);
  if (!session?.username) return json(401, { error: "Unauthorized" });

  try {
    initFirebase();
    const db = admin.firestore();
    const limit = Math.min(Number(event.queryStringParameters?.limit || 40), 100);
    const snap = await db.collection("submissions").orderBy("createdAt", "desc").limit(limit).get();
    const items = snap.docs.map((doc) => {
      const d = doc.data() || {};
      return {
        id: doc.id,
        firstName: d.firstName || "",
        lastName: d.lastName || "",
        email: d.email || "",
        phone: d.phone || "",
        state: d.state || "",
        status: d.status || "new",
        issued_id: d.issued_id || null,
        confirmationEmailSent: !!d.confirmationEmailSent,
        followup_sent: !!d.followup_sent,
        paid: !!d.paid,
        createdAt: d.createdAt || null,
        updatedAt: d.updatedAt || null,
        flows: d.flows || {},
      };
    });

    const stats = {
      total: items.length,
      new: items.filter((i) => i.status === "new").length,
      processing: items.filter((i) => i.status === "processing").length,
      completed: items.filter((i) => i.status === "completed").length,
      failed: items.filter((i) => i.status === "failed").length,
      manual: items.filter((i) => i.status === "manual").length,
    };

    return json(200, { ok: true, items, stats });
  } catch (err) {
    console.error("list-submissions error", err);
    return json(500, { error: err.message || "Server error" });
  }
}
