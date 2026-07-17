/**
 * Stripe webhook — records payments/<payment_intent_id> in Firestore.
 * Set STRIPE_WEBHOOK_SECRET + FIREBASE_SERVICE_ACCOUNT_JSON in Netlify.
 */
const admin = require("firebase-admin");

function initFirebase() {
  if (admin.apps.length) return;
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
  if (!raw) throw new Error("FIREBASE_SERVICE_ACCOUNT_JSON missing");
  admin.initializeApp({ credential: admin.credential.cert(JSON.parse(raw)) });
}

exports.handler = async function handler(event) {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method not allowed" };
  }

  const paywall = (process.env.PAYWALL_ENABLED || "false").toLowerCase() === "true";
  if (!paywall) {
    return { statusCode: 200, body: JSON.stringify({ ok: true, ignored: true }) };
  }

  const stripeKey = process.env.STRIPE_SECRET_KEY;
  const whSecret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!stripeKey || !whSecret) {
    return { statusCode: 500, body: "Stripe webhook not configured" };
  }

  try {
    const stripe = require("stripe")(stripeKey);
    const sig = event.headers["stripe-signature"] || event.headers["Stripe-Signature"];
    const rawBody = event.isBase64Encoded
      ? Buffer.from(event.body, "base64").toString("utf8")
      : event.body;
    const stripeEvent = stripe.webhooks.constructEvent(rawBody, sig, whSecret);

    if (stripeEvent.type === "payment_intent.succeeded") {
      const pi = stripeEvent.data.object;
      initFirebase();
      await admin.firestore().collection("payments").doc(pi.id).set(
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

    return { statusCode: 200, body: JSON.stringify({ received: true }) };
  } catch (err) {
    console.error(err);
    return { statusCode: 400, body: `Webhook Error: ${err.message}` };
  }
};
