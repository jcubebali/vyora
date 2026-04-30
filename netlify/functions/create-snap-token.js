const https = require("https");

exports.handler = async (event, context) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method Not Allowed" };
  }

  const { plan, period, name, email, uid } = JSON.parse(event.body);

  const PRICES = {
    basic:  { monthly: 99000,  yearly: 708000 },
    pro:    { monthly: 199000, yearly: 1428000 },
    elite:  { monthly: 499000, yearly: 3588000 },
  };

  const amount = PRICES[plan][period];
  const orderId = `NEXUS-${uid.slice(0,8)}-${Date.now()}`;

  const payload = JSON.stringify({
    transaction_details: { order_id: orderId, gross_amount: amount },
    customer_details: { first_name: name || "Trader", email: email || "" },
    item_details: [{ id: plan, price: amount, quantity: 1,
      name: `Nexus Trade ${plan.charAt(0).toUpperCase()+plan.slice(1)} (${period})` }],
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

    const req = https.request(options, (res) => {
      let body = "";
      res.on("data", (chunk) => body += chunk);
      res.on("end", () => {
        try {
          const result = JSON.parse(body);
          if (result.token) {
            resolve({
              statusCode: 200,
              headers: { "Access-Control-Allow-Origin": "*" },
              body: JSON.stringify({ token: result.token, orderId }),
            });
          } else {
            resolve({ statusCode: 500, body: JSON.stringify({ error: body }) });
          }
        } catch(e) {
          resolve({ statusCode: 500, body: JSON.stringify({ error: e.message }) });
        }
      });
    });

    req.on("error", (e) => resolve({ statusCode: 500, body: e.message }));
    req.write(payload);
    req.end();
  });
};
