"""A minimal model call for the headless phase: OpenRouter through the OpenAI
SDK, with the reasoning-effort parameter and a cost estimate from a small price
table. The app's model layer replaces this in phase 2 (streaming, telemetry,
the turn ladder); the Session only needs `llm(system, user) -> (text, usage)`.
"""
from __future__ import annotations

import os
import time

PRICES_PER_M = {   # (input, output) USD per million tokens - the template's model_properties
    "meta/muse-spark-1.3": (1.25, 4.25),
    "x-ai/grok-4.6": (2.00, 6.00),
    "z-ai/glm-5.3": (1.40, 4.40),
    "z-ai/glm-5.3-flash": (0.15, 0.50),
    "google/gemini-3.8-flash": (0.75, 3.75),
    "deepseek/deepseek-v4-flash-0731": (0.44, 1.32),
}


def make_llm(model: str, effort: str = "medium", max_tokens: int = 16000, api_key: str | None = None,
             base_url: str = "https://openrouter.ai/api/v1", retries: int = 3):
    from openai import OpenAI
    client = OpenAI(api_key=api_key or os.environ["OPENROUTER_API_KEY"], base_url=base_url)
    pin, pout = PRICES_PER_M.get(model, (0.0, 0.0))

    def llm(system: str, user: str, **hints):          # hints (review=True on a self-review turn) are the app's concern; the CLI has one model
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if effort and effort != "none":
            body["extra_body"] = {"reasoning": {"effort": effort}}
        last = None
        for attempt in range(retries):
            try:
                t0 = time.time()
                r = client.chat.completions.create(**body)
                text = (r.choices[0].message.content or "") if r.choices else ""
                u = getattr(r, "usage", None)
                pt = int(getattr(u, "prompt_tokens", 0) or 0); ct = int(getattr(u, "completion_tokens", 0) or 0)
                return text, {"model": model, "prompt_tokens": pt, "completion_tokens": ct,
                              "cost": round(pt * pin / 1e6 + ct * pout / 1e6, 5), "seconds": round(time.time() - t0, 1)}
            except Exception as exc:                          # noqa: BLE001
                last = exc
                time.sleep((5, 20, 60)[min(attempt, 2)])
        raise RuntimeError(f"model call failed after {retries} attempts: {last}")

    return llm
