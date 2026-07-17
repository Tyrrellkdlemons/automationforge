/**
 * Create a Stripe PaymentIntent when PAYWALL_ENABLED=true.
 * Payment provider is selectable via PAYMENT_PROVIDER=stripe|manual
 * (GoDaddy/other: set PAYMENT_PROVIDER=manual and collect offline, or plug your own function later).
 */
exports.handler = async function handler(event) {
  const headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type, x-submission-secret",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
  };
  if (event.httpMethod === "OPTIONS") return { statusCode: 204, headers, body: "" };
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers, body: JSON.stringify({ error: "Method not allowed" }) };
  }

  const paywall = (process.env.PAYWALL_ENABLED || "false").toLowerCase() === "true";
  const provider = (process.env.PAYMENT_PROVIDER || "stripe").toLowerCase();

  if (!paywall) {
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ ok: true, paywallEnabled: false, message: "Paywall off — no payment needed" }),
    };
  }

  if (provider !== "stripe") {
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        ok: true,
        paywallEnabled: true,
        provider,
        mode: "manual",
        message:
          "PAYMENT_PROVIDER is not stripe. Collect payment via GoDaddy/other, then submit with paymentRef.",
      }),
    };
  }

  const secret = process.env.STRIPE_SECRET_KEY;
  if (!secret) {
    return { statusCode: 500, headers, body: JSON.stringify({ error: "STRIPE_SECRET_KEY missing" }) };
  }

  let amount = 1999;
  let currency = "usd";
  try {
    const body = JSON.parse(event.body || "{}");
    if (body.amount) amount = Number(body.amount);
    if (body.currency) currency = String(body.currency);
  } catch (_) {}

  try {
    const stripe = require("stripe")(secret);
    const intent = await stripe.paymentIntents.create({
      amount,
      currency,
      automatic_payment_methods: { enabled: true },
      metadata: { product: "peeezmachine_appflow_submission" },
    });
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        ok: true,
        paywallEnabled: true,
        provider: "stripe",
        clientSecret: intent.client_secret,
        paymentIntentId: intent.id,
      }),
    };
  } catch (err) {
    return { statusCode: 500, headers, body: JSON.stringify({ error: err.message }) };
  }
};
