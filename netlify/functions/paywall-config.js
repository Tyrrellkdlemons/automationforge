/**
 * Public config for the submit page (paywall flag + publishable key). No secrets.
 */
exports.handler = async function handler() {
  const paywall = (process.env.PAYWALL_ENABLED || "false").toLowerCase() === "true";
  const provider = (process.env.PAYMENT_PROVIDER || "stripe").toLowerCase();
  return {
    statusCode: 200,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store",
    },
    body: JSON.stringify({
      paywallEnabled: paywall,
      paymentProvider: provider,
      stripePublishableKey: process.env.STRIPE_PUBLISHABLE_KEY || "",
      amountCents: Number(process.env.PAYWALL_AMOUNT_CENTS || "1999"),
      amountLabel: process.env.PAYWALL_AMOUNT_LABEL || "$19.99",
    }),
  };
};
