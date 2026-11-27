"""The Stripe webhook (web_app/subscription_routes.py) against the real `stripe` library: events of invented data,
signed the way Stripe signs them and posted to the route on a test app. The database's add_funds is a stand-in that
records what it was asked.

Why: the library's own objects stopped being dicts in 15.0, and the route called .get on one - a 500 at every paid
session, nothing credited (2026-11-27). The app-path suite fakes the library and could not see it; this one runs
whichever version is installed.

Skips (exit 0, one line) where the library is not installed: the self-hosted edition has no billing.

    python3 tests/analyst/test_stripe_webhook.py
"""
import hashlib
import hmac
import importlib.util
import json
import logging
import os
import sys
import time
import types

if importlib.util.find_spec("stripe") is None:
    print("stripe not installed: the webhook suite against the real library is skipped")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "web_app"))
SECRET = "whsec_field_trial"
os.environ["STRIPE_WEBHOOK_SECRET"] = SECRET                # the route reads it when it is imported

credits = []
credit_answer = {"ok": True}


def add_funds(**asked):
    credits.append(asked)
    return dict(credit_answer)


# the route's other imports, stood in for: no database and no sign-in here
database = types.ModuleType("auth.supabase_client")
for name in ("set_user_subscription", "get_user_subscription", "get_balance", "get_monthly_usage", "get_tier_limits"):
    setattr(database, name, lambda *a, **k: {"ok": True})
database.add_funds = add_funds
sign_in = types.ModuleType("auth")
sign_in.requires_auth = lambda f: f
sign_in.get_current_user_id = lambda: "auth0|grower-a"
builder = types.ModuleType("llm_config_builder")
builder.build_user_config = lambda *a, **k: {}
sys.modules.update({"auth": sign_in, "auth.supabase_client": database, "llm_config_builder": builder})

import flask  # noqa: E402
import stripe  # noqa: E402
import subscription_routes  # noqa: E402

logging.disable(logging.CRITICAL)                           # the route logs what it refuses; not this suite's output
app = flask.Flask("webhook")
app.register_blueprint(subscription_routes.subscription_bp)
client = app.test_client()
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:300]}"))


def event(kind="checkout.session.completed", status="paid", session="cs_test_a1", payment="pi_test_a1", cents=5000, name="First Person"):
    """A Checkout Session event as Stripe sends it for a card payment of account credit, of invented data."""
    paid_for = {
        "id": session, "object": "checkout.session", "adaptive_pricing": {"enabled": True},
        "amount_subtotal": cents, "amount_total": cents, "cancel_url": "https://app.example.test/api/payment-cancelled",
        "client_reference_id": None, "created": 1800000000, "currency": "usd", "customer": None, "customer_creation": "if_required",
        "customer_details": {"email": "grower@example.test", "name": name, "phone": None, "tax_exempt": "none", "tax_ids": []},
        "customer_email": None, "expires_at": 1800086400, "livemode": True,
        "metadata": {"auth0_id": "auth0|grower-a", "amount": str(cents // 100)}, "mode": "payment",
        "payment_intent": payment, "payment_method_types": ["card", "link"], "payment_status": status, "status": "complete",
        "success_url": "https://app.example.test/api/payment-success?session_id={CHECKOUT_SESSION_ID}",
        "total_details": {"amount_discount": 0, "amount_shipping": 0, "amount_tax": 0}, "ui_mode": "hosted"}
    return json.dumps({"id": "evt_test_a1", "object": "event", "api_version": "2025-09-30.clover", "created": 1800000000,
                       "data": {"object": paid_for}, "livemode": True, "pending_webhooks": 1,
                       "request": {"id": None, "idempotency_key": None}, "type": kind}, ensure_ascii=False)


def signed(payload, secret=SECRET, age=0):
    """The Stripe-Signature header for a payload: the time and the HMAC-SHA256 of 'time.payload' under the secret."""
    at = int(time.time()) - age
    return f"t={at},v1={hmac.new(secret.encode(), f'{at}.{payload}'.encode(), hashlib.sha256).hexdigest()}"


def deliver(payload, signature):
    return client.post("/api/stripe-webhook", data=payload, headers={"Stripe-Signature": signature} if signature else {})


print(f"stripe {getattr(stripe, 'VERSION', '?')}")
paid = event()
answer = deliver(paid, signed(paid))
check("a paid session, signed as Stripe signs it: acknowledged and credited once - the person, $50, the session as the reference, the payment as the idempotency key",
      answer.status_code == 200 and answer.get_json() == {"received": True}
      and credits == [{"auth0_id": "auth0|grower-a", "amount": 50.0, "source": "stripe", "reference": "cs_test_a1", "idempotency_key": "pi_test_a1", "skip_validation": True}],
      (answer.status_code, answer.get_data(as_text=True)[:200], credits))
answer = deliver(paid, signed(paid))
check("the same event delivered again (Stripe repeats an event until it is acknowledged) asks under the same key, which the database credits once",
      answer.status_code == 200 and [c["idempotency_key"] for c in credits] == ["pi_test_a1", "pi_test_a1"], (answer.status_code, credits))

del credits[:]
unpaid = event(status="unpaid", session="cs_test_b1", payment="pi_test_b1")
answer = deliver(unpaid, signed(unpaid))
check("a session completed but not paid yet (a delayed method) is acknowledged and not credited", answer.status_code == 200 and credits == [], (answer.status_code, credits))
later = event(kind="checkout.session.async_payment_succeeded", session="cs_test_b1", payment="pi_test_b1")
answer = deliver(later, signed(later))
check("... and credited when Stripe reports the payment in", answer.status_code == 200 and [c["reference"] for c in credits] == ["cs_test_b1"], (answer.status_code, credits))
other = json.dumps({"id": "evt_test_c1", "object": "event", "type": "payment_intent.created", "data": {"object": {"id": "pi_test_c1", "object": "payment_intent"}}})
answer = deliver(other, signed(other))
check("another event type is acknowledged and ignored", answer.status_code == 200 and len(credits) == 1, (answer.status_code, credits))
named = event(session="cs_test_d1", payment="pi_test_d1", name="First Person of Plötville")
answer = deliver(named, signed(named))
check("a name with a letter beyond ASCII, sent as UTF-8: the signature holds over the bytes as they came, and the session is credited",
      "ö" in named and answer.status_code == 200 and [c["reference"] for c in credits] == ["cs_test_b1", "cs_test_d1"], (answer.status_code, answer.get_data(as_text=True)[:200], credits))

del credits[:]
for name, payload, signature in (
        ("signed with another secret", paid, signed(paid, "whsec_someone_else")),
        ("changed after it was signed", paid.replace('"amount_total": 5000', '"amount_total": 500000'), signed(paid)),
        ("with no signature", paid, None),
        ("signed ten minutes ago (the library allows five: a recorded call cannot be played again later)", paid, signed(paid, age=600))):
    answer = deliver(payload, signature)
    check(f"a call {name} is refused with a 400 and credits nothing", answer.status_code == 400 and answer.get_json() == {"error": "Invalid signature"} and credits == [],
          (answer.status_code, answer.get_data(as_text=True)[:200], credits))
answer = deliver("not json", signed("not json"))
check("signed text that is not JSON is a 400", answer.status_code == 400 and answer.get_json() == {"error": "Invalid payload"}, (answer.status_code, answer.get_data(as_text=True)[:200]))

del credits[:]
credit_answer.update(ok=False, error="database away")
answer = deliver(paid, signed(paid))
credit_answer.clear()
credit_answer.update(ok=True)
again = deliver(paid, signed(paid))
check("a credit the database refuses is answered 500 with the reason, so Stripe shows the delivery failed and sends the event again; the next delivery credits",
      answer.status_code == 500 and answer.get_json() == {"error": "Not credited: database away"} and again.status_code == 200 and len(credits) == 2,
      (answer.status_code, answer.get_data(as_text=True)[:200], again.status_code, credits))

n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
