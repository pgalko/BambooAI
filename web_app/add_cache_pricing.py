#!/usr/bin/env python3
"""
add_cache_pricing.py - declare what a cached token costs, per model.

WHY THIS IS NOT HARD-CODED NUMBERS

`log_manager` falls back to Anthropic's ratios when a model declares no cache
pricing: reads at 0.1x input, writes at 1.25x. That is right for Anthropic,
close for OpenAI, and wrong for Gemini and xAI - and being wrong here is silent.
The bill comes out confident and incorrect.

Rates are therefore DERIVED from each model's declared `prompt_tokens` using its
provider's published ratio, rather than typed in as absolutes. Two consequences
worth having: if you revise a base price the cache price stays consistent
automatically, and the ratio - which is the thing that is actually documented by
providers - is visible in one table instead of scattered across 26 entries.

All costs in this file are PER 1000 TOKENS, matching the existing
prompt_tokens / completion_tokens convention.

RATIOS (check against current provider pricing before you rely on the billing)

  anthropic   read 0.10x   write 1.25x   explicit cache_control breakpoints;
                                         the 5-minute write premium is real and
                                         is the only write premium that applies
                                         anywhere in this table
  openai      read 0.10x   write 1.00x   implicit above ~1024 tokens; no write
                                         premium is billed
  gemini      read 0.25x   write 1.00x   implicit caching. NOTE the ratio is
                                         2.5x Anthropic's, so leaving Gemini to
                                         the default under-bills it by 60%
  xai/grok    read 0.25x   write 1.00x   implicit, affinity-sensitive
  deepseek    read 0.10x   write 1.00x   DIRECT API (deepseek-chat,
                                         deepseek-reasoner): published
                                         hit price is 1/10 of miss
  deepseek_or read 0.008x  write 1.00x   OPENROUTER route (deepseek/...
                                         slugs): EMPIRICAL - reconciled
                                         row-for-row against the
                                         openrouter activity export,
                                         session 2026-08-12 23:00+ (the
                                         1/10 guess overstated cached
                                         reads ~13x on this route)
  moonshot    read 0.10x   write 1.00x   automatic context caching
  mistral     none                       no published cached-token rate; left
                                         undeclared so it falls back rather
                                         than asserting a number
  local       none                       zero cost either way

A model routed through OpenRouter takes the ratio of the model UNDERNEATH it -
OpenRouter passes the provider's economics through - so `anthropic/claude-...`
gets Anthropic's write premium and `deepseek/...` does not.
"""

import json
import sys

RATIOS = {
    "anthropic": (0.10, 1.25),
    "openai":    (0.10, 1.00),
    "gemini":    (0.25, 1.00),
    "gemini_or": (0.10, 1.00),   # google/gemini-3.x via openrouter: page-listed
                                 # cache read 0.10x (Gemini 3 implicit caching),
                                 # vs 0.25x on the native-API generation entries
    "xai":       (0.25, 1.00),
    "deepseek":  (0.10, 1.00),
    "deepseek_or": (0.008, 1.00),
    "moonshot":  (0.10, 1.00),
}


def family(model):
    """The provider whose cache economics apply, from the model name.

    Matched on the name rather than the roster's `provider` field because the
    same model can be reached directly or through OpenRouter, and the economics
    follow the model, not the route.
    """
    m = model.lower()
    if "claude" in m or m.startswith("anthropic/"):
        return "anthropic"
    if "gpt-" in m or m.startswith("openai/") or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    if m.startswith("google/gemini"):
        return "gemini_or"            # openrouter-routed slug, 3.x economics
    if "gemini" in m:
        return "gemini"
    if "grok" in m or m.startswith("x-ai/"):
        return "xai"
    if m.startswith("deepseek/"):
        return "deepseek_or"          # openrouter-routed slug
    if "deepseek" in m and not m.startswith("/"):
        return "deepseek"             # direct API
    if "kimi" in m or m.startswith("moonshotai/"):
        return "moonshot"
    return None                      # mistral, codestral, local paths


def annotate(model_properties):
    """Add cache_read_tokens / cache_write_tokens where a ratio is known."""
    touched, skipped = [], []
    for name, props in model_properties.items():
        fam = family(name)
        inp = props.get("prompt_tokens")
        if fam is None or not inp:
            # No published ratio, or a free/local model. Declaring nothing is
            # better than declaring a guess: the fallback is at least documented.
            skipped.append(name)
            continue
        read_r, write_r = RATIOS[fam]
        props["cache_read_tokens"] = round(inp * read_r, 8)
        props["cache_write_tokens"] = round(inp * write_r, 8)
        touched.append((name, fam, props["cache_read_tokens"], props["cache_write_tokens"]))
    return touched, skipped


def main(path):
    with open(path, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    crlf = "\r\n" in raw
    cfg = json.loads(raw)

    touched, skipped = annotate(cfg.get("model_properties", {}))

    out = json.dumps(cfg, indent=2)
    if crlf:
        out = out.replace("\n", "\r\n")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)

    print(f"annotated {len(touched)} models:\n")
    for name, fam, r, w in touched:
        premium = "  <- write premium applies" if w > cfg["model_properties"][name]["prompt_tokens"] else ""
        print(f"  {name:<42} {fam:<10} read={r:<10} write={w}{premium}")
    if skipped:
        print(f"\nleft to the fallback ({len(skipped)}): {', '.join(skipped)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "web_app/LLM_CONFIG_template.json")