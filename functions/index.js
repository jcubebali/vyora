const functions = require("firebase-functions");
const admin = require("firebase-admin");
const https = require("https");

admin.initializeApp();

// ── Generate Midtrans Snap Token ──────────────
exports.createSnapToken = functions.https.onCall(async (data, context) => {
  // Cek user login
  if (!context.auth) {
    throw new functions.https.HttpsError("unauthenticated", "Login dulu!");
  }

  const { plan, period, name, email } = data;

  const PRICES = {
    basic:  { monthly: 99000,  yearly: 708000 },
    pro:    { monthly: 199000, yearly: 1428000 },
    elite:  { monthly: 499000, yearly: 3588000 },
  };

  const amount = PRICES[plan][period];
  const orderId = `NEXUS-${context.auth.uid.slice(0,8)}-${Date.now()}`;

  const payload = JSON.stringify({
    transaction_details: {
      order_id: orderId,
      gross_amount: amount,
    },
    customer_details: {
      first_name: name || "Trader",
      email: email || "",
    },
    item_details: [{
      id: plan,
      price: amount,
      quantity: 1,
      name: `Nexus Trade ${plan.charAt(0).toUpperCase()+plan.slice(1)} (${period})`,
    }],
  });

  // Server key Midtrans (sandbox)
  const serverKey = "Mid-server-DQVklBw9VvZIoqBB6fQSMN6o";
  const encoded = Buffer.from(serverKey + ":").toString("base64");

  return new Promise((resolve, reject) => {
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
            // Simpan order ke Firestore
            admin.firestore().collection("payments").add({
              uid: context.auth.uid,
              orderId,
              plan,
              period,
              amount,
              status: "pending",
              createdAt: admin.firestore.FieldValue.serverTimestamp(),
            });
            resolve({ token: result.token, orderId });
          } else {
            reject(new functions.https.HttpsError("internal", "Gagal dapat token: " + body));
          }
        } catch(e) {
          reject(new functions.https.HttpsError("internal", e.message));
        }
      });
    });

    req.on("error", (e) => reject(new functions.https.HttpsError("internal", e.message)));
    req.write(payload);
    req.end();
  });
});

// ── Midtrans Webhook ──────────────────────────
exports.midtransWebhook = functions.https.onRequest(async (req, res) => {
  const { order_id, transaction_status, fraud_status } = req.body;

  if (transaction_status === "capture" || transaction_status === "settlement") {
    if (fraud_status === "accept" || !fraud_status) {
      // Cari payment dan update plan user
      const payments = await admin.firestore()
        .collection("payments")
        .where("orderId", "==", order_id)
        .get();

      if (!payments.empty) {
        const payment = payments.docs[0].data();
        const days = payment.period === "yearly" ? 365 : 30;

        // Update user plan
        await admin.firestore().collection("users").doc(payment.uid).update({
          plan: payment.plan,
          subscriptionEndsAt: new Date(Date.now() + days * 24*60*60*1000),
        });

        // Update payment status
        await payments.docs[0].ref.update({ status: "paid" });
      }
    }
  }

  res.json({ status: "ok" });
});
