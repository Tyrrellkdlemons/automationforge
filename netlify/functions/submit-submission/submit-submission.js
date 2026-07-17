/**
 * Netlify Function: create a Firestore submission from the public form.
 * Requires state. Optional street/city/zip. Optional paymentIntentId when paywall on.
 */
const admin = require("firebase-admin");

let initTried = false;

const US_STATES = new Set([
  "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM",
  "NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA",
  "WV","WI","WY",
]);

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
  if (!raw) throw new Error("FIREBASE_SERVICE_ACCOUNT_JSON is not set");
  admin.initializeApp({ credential: admin.credential.cert(JSON.parse(raw)) });
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
  if (event.httpMethod === "OPTIONS") return json(204, {});
  if (event.httpMethod !== "POST") return json(405, { error: "Method not allowed" });

  try {
    const expected = process.env.SUBMISSION_SECRET || "";
    const provided =
      event.headers["x-submission-secret"] || event.headers["X-Submission-Secret"] || "";
    if (!expected || provided !== expected) return json(401, { error: "Unauthorized" });

    const body = parseBody(event);
    const firstName = String(body.firstName || "").trim();
    const lastName = String(body.lastName || "").trim();
    const email = String(body.email || "").trim().toLowerCase();
    const dob = String(body.dob || body.dateOfBirth || "").trim();
    const phone = String(body.phone || "").trim();
    const state = String(body.state || "").trim().toUpperCase();
    const street = String(body.street || (body.address && body.address.street) || "").trim();
    const city = String(body.city || (body.address && body.address.city) || "").trim();
    const zip = String(body.zip || (body.address && body.address.zip) || "").trim();
    const paymentIntentId = String(body.paymentIntentId || body.paymentRef || "").trim();

    if (!firstName || !lastName) return json(400, { error: "First name and last name are required" });
    if (!email || !email.includes("@")) return json(400, { error: "A valid email is required" });
    if (!isValidDob(dob)) return json(400, { error: "Date of birth must be YYYY-MM-DD" });
    if (!US_STATES.has(state)) return json(400, { error: "A valid US state is required" });

    const paywall = (process.env.PAYWALL_ENABLED || "false").toLowerCase() === "true";
    const provider = (process.env.PAYMENT_PROVIDER || "stripe").toLowerCase();
    let paid = false;

    initFirebase();
    const db = admin.firestore();

    if (paywall) {
      if (provider === "stripe") {
        if (!paymentIntentId) return json(402, { error: "Payment required" });
        const payDoc = await db.collection("payments").doc(paymentIntentId).get();
        // Also accept client-confirmed intents when webhook hasn't landed yet: verify via Stripe
        if (payDoc.exists && payDoc.data().status === "succeeded") {
          paid = true;
        } else if (process.env.STRIPE_SECRET_KEY) {
          const stripe = require("stripe")(process.env.STRIPE_SECRET_KEY);
          const pi = await stripe.paymentIntents.retrieve(paymentIntentId);
          if (pi.status === "succeeded") {
            paid = true;
            await db.collection("payments").doc(paymentIntentId).set(
              {
                status: "succeeded",
                amount: pi.amount,
                currency: pi.currency,
                createdAt: new Date().toISOString(),
                provider: "stripe",
              },
              { merge: true }
            );
          }
        }
        if (!paid) return json(402, { error: "Payment not completed" });
      } else {
        // GoDaddy / manual / other — require a payment reference string
        if (!paymentIntentId) {
          return json(402, {
            error: "Payment reference required (GoDaddy/manual). Pass paymentRef after collecting payment.",
          });
        }
        paid = true;
        await db.collection("payments").doc(paymentIntentId).set(
          {
            status: "recorded",
            provider,
            createdAt: new Date().toISOString(),
          },
          { merge: true }
        );
      }
    }

    const now = new Date().toISOString();
    const doc = {
      firstName,
      lastName,
      email,
      phone,
      dob,
      state,
      address: { street, city, state, zip, country: "United States" },
      status: "new",
      issued_id: null,
      paid,
      paymentIntentId: paymentIntentId || null,
      paymentProvider: paywall ? provider : null,
      followup_sent: false,
      followup_history: [],
      confirmationEmailSent: false,
      flows: {
        newsletter: { status: "pending", error: null },
        saas_trial: { status: "pending", error: null },
        job_profile: { status: "pending", error: null },
      },
      manualOverride: false,
      manualLogs: [],
      randomized_fields: {},
      createdAt: now,
      updatedAt: now,
    };

    const ref = await db.collection("submissions").add(doc);
    return json(200, {
      ok: true,
      submissionId: ref.id,
      message:
        "Submission received. You will receive your unique ID by email shortly after processing starts.",
    });
  } catch (err) {
    console.error("submit-submission error", err);
    return json(500, { error: err.message || "Server error" });
  }
};
