import assert from "node:assert/strict";
import { test } from "node:test";

import { shouldIncludeSms } from "../prefilter.ts";

test("bank debit alert from a DLT sender is included", () => {
  assert.equal(
    shouldIncludeSms({
      address: "AD-HDFCBK",
      body: "Rs.500.00 debited from A/c XX1234 on 12-06-26 to VPA shop@okhdfcbank. Avl Bal Rs.9,500.00",
    }),
    true
  );
});

test("OTP from the same bank sender is excluded (never leaves the device)", () => {
  assert.equal(
    shouldIncludeSms({
      address: "AD-HDFCBK",
      body: "Dear Customer, your OTP for login is 482913. Do not share this with anyone.",
    }),
    false
  );
});

test("a transaction-shaped message from a personal phone number is excluded", () => {
  assert.equal(
    shouldIncludeSms({
      address: "+919876543210",
      body: "Hey, I credited you Rs.500 for dinner, send your account details",
    }),
    false
  );
});

test("a bank sender with no transaction language is excluded", () => {
  assert.equal(
    shouldIncludeSms({
      address: "AD-HDFCBK",
      body: "Your statement is now available. Visit netbanking to view it.",
    }),
    false
  );
});

test("sensitive keywords win even when transaction keywords are also present", () => {
  assert.equal(
    shouldIncludeSms({
      address: "AD-HDFCBK",
      body: "Your account password has been reset. If this was not you, call us. Rs.0.00 debited.",
    }),
    false
  );
});

test("UPI spend alert from a short alphanumeric sender code is included", () => {
  assert.equal(
    shouldIncludeSms({
      address: "SBIUPI",
      body: "You have spent Rs 250.00 from account ending 1234 to Big Bazaar on 12-06-2026. UPI Ref No 123456789012",
    }),
    true
  );
});
