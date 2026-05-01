const https = require("https");

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") return res.status(200).end();
  if (req.method !== "POST") return res.status(405).json({ error: "Method Not Allowed" });

  const { plan, period, name, email, uid } = req.body;

  const PRICES = {
    basic:  { monthly: 99000,  yearly: 708000 },
    pro:    { monthly: 199000, yearly: 1428000 },
    elite:  { monthly: 499000, yearly: 3588000 },
  };

  const amount = PRICES[plan]?.[period] || 199000;
  const orderId = `VYORA-${uid.slice(0,8)}-${Date.now()}`;

  const payload = JSON.stringify({
    transaction_details: { order_id: orderId, gross_amount: amount },
    customer_details: { first_name: name || "Trader", email: email || "" },
    item_details: [{ id: plan, price: amount, quantity: 1,
      name: `Vyora ${plan.charAt(0).toUpperCase()+plan.slice(1)} (${period})` }],
  });

  const serverKey = "Mid-server-DQVklBw9VvZIoqBB6fQSMN6o";
  const encoded = Buffer.from(serverKey + ":").toString("base64");

  return new Promise((resolve) => {
    const options = {
      hostname: "app.sandbox.midtrans.com",
      path: "/snap/v1/transactions",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Basic ${encoded}`,
        "Content-Length": Buffer.byteLength(payload),
      },
    };

    const request = https.request(options, (response) => {
      let body = "";
      response.on("data", (chunk) => body += chunk);
      response.on("end", () => {
        try {
          const result = JSON.parse(body);
          if (result.token) {
            res.status(200).json({ token: result.token, orderId });
          } else {
            res.status(500).json({ error: body });
          }
        } catch(e) {
          res.status(500).json({ error: e.message });
        }
        resolve();
      });
    });

    request.on("error", (e) => { res.status(500).json({ error: e.message }); resolve(); });
    request.write(payload);
    request.end();
  });
}
