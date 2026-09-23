import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { createPhoneOTPSender } from "../src/phone.js";

function readJsonBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
    });
    req.on("end", () => resolve(raw ? JSON.parse(raw) : {}));
  });
}

// Stands in for whatsapp-sender's /send (this module makes a real HTTP
// call, unlike whatsapp-sender's own currently-pure-logic tests).
async function withStubGateway(handler, run) {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

test("posts the exact {phone, message} body and x-api-key header, resolves on a sent status", async () => {
  let received;
  await withStubGateway(
    async (req, res) => {
      received = { headers: req.headers, body: await readJsonBody(req) };
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "sent" }));
    },
    async (gatewayUrl) => {
      const sendPhoneOTP = createPhoneOTPSender({ gatewayUrl, apiKey: "secret-key" });
      await assert.doesNotReject(sendPhoneOTP("+15551234567", "123456"));
    }
  );

  assert.equal(received.headers["x-api-key"], "secret-key");
  assert.deepEqual(received.body, {
    phone: "+15551234567",
    message: "Your JobsHub verification code is 123456.",
  });
});

test("omits the x-api-key header when no key is configured", async () => {
  let received;
  await withStubGateway(
    async (req, res) => {
      received = req.headers;
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "sent" }));
    },
    async (gatewayUrl) => {
      const sendPhoneOTP = createPhoneOTPSender({ gatewayUrl, apiKey: "" });
      await sendPhoneOTP("+15551234567", "123456");
    }
  );
  assert.equal(received["x-api-key"], undefined);
});

test("throws when the gateway responds with a non-sent status", async () => {
  await withStubGateway(
    async (req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "queued" }));
    },
    async (gatewayUrl) => {
      const sendPhoneOTP = createPhoneOTPSender({ gatewayUrl });
      await assert.rejects(sendPhoneOTP("+15551234567", "123456"));
    }
  );
});

test("throws when the gateway responds with a non-2xx status", async () => {
  await withStubGateway(
    async (req, res) => {
      res.writeHead(503, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "WhatsApp session not ready" }));
    },
    async (gatewayUrl) => {
      const sendPhoneOTP = createPhoneOTPSender({ gatewayUrl });
      await assert.rejects(sendPhoneOTP("+15551234567", "123456"));
    }
  );
});

test("throws when WHATSAPP_GATEWAY_URL is not configured, without making a request", async () => {
  const sendPhoneOTP = createPhoneOTPSender({ gatewayUrl: "" });
  await assert.rejects(sendPhoneOTP("+15551234567", "123456"));
});

test("isValidPhoneNumber accepts only +<country code><number>", async () => {
  const { isValidPhoneNumber } = await import("../src/phone.js");
  assert.equal(isValidPhoneNumber("+919902065845"), true);
  assert.equal(isValidPhoneNumber("+15551234567"), true);
  for (const bad of ["+019902065845", "9902065845", "+91 99020 65845", "", null, "+1234"]) {
    assert.equal(isValidPhoneNumber(bad), false, String(bad));
  }
});

test("a gateway 'not_on_whatsapp' answer becomes a 400 the user can read, not a 500", async () => {
  const { APIError } = await import("better-auth/api");
  await withStubGateway(
    (req, res) => {
      res.writeHead(422, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "not_on_whatsapp" }));
    },
    async (gatewayUrl) => {
      const sendPhoneOTP = createPhoneOTPSender({ gatewayUrl, apiKey: "k" });
      await assert.rejects(sendPhoneOTP("+15551234567", "123456"), (err) => {
        assert.ok(err instanceof APIError, "expected an APIError");
        assert.equal(err.statusCode, 400);
        assert.match(err.body?.message ?? "", /isn't on WhatsApp/);
        return true;
      });
    },
  );
});
