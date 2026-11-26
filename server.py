"""scarecrow-consult — MCP server exposing the ScareCrow consultation brains.

Owner build (2026-11-26): "make it a real mcp tool".

Consultation brains via the sunny-scarecrow balancer on Lappy (:8486), which fans
out to the bridge adapter (:8507 — browser-session brains) and the cloud lanes
(nvapi, openrouter). Lane pinning: model == lane name selects THAT brain exactly
(balancer.py line 981: direct-name access bypasses the round-robin).

Lanes (catalog + recorded identity):
  bridge-chatgpt  — GPT-6 (OpenAI, via bridge)        <- default consultation brain
  bridge-deepseek — DeepSeek (via bridge)
  bridge-mistral  — Mistral (via bridge)
  bridge-qwen     — Qwen (via bridge)
  bridge-gemini   — Gemini (via bridge)
  bridge-grok     — Grok (via bridge)
  bridge-kimi     — Kimi (via bridge)
  nvapi           — nemotron-3.5-super-120b (NVIDIA cloud)
  openrouter      — free rotating pool
  scarecrow       — round-robin over all lanes (default balancer behaviour)

Notes: upstreams rotate free reasoning models — max_tokens must be generous
(>= 6000) and null-content responses are retried (the balancer picks a
different upstream per call). The upstream "model" field is always reported
back alongside the answer so the consulted brain is never in doubt.
"""

import json
import urllib.request
from typing import Any

from mcp.server.fastmcp import FastMCP

PROXY = "http://192.168.0.33:8486/v1/chat/completions"
KEY = "evo-local"
DEFAULT_LANE = "bridge-chatgpt"

LANES: dict[str, str] = {
    "bridge-chatgpt": "GPT-6 (OpenAI, via browser bridge) — default consultation brain",
    "bridge-deepseek": "DeepSeek (via browser bridge)",
    "bridge-mistral": "Mistral (via browser bridge)",
    "bridge-qwen": "Qwen (via browser bridge)",
    "bridge-gemini": "Gemini (via browser bridge)",
    "bridge-grok": "Grok (via bridge)",
    "bridge-kimi": "Kimi (via bridge)",
    "nvapi": "nemotron-3.5-super-120b (NVIDIA cloud)",
    "openrouter": "free rotating pool (openrouter/free)",
    "scarecrow": "round-robin over all lanes (weights: nvapi 100, openrouter 50, bridges 10)",
}

mcp = FastMCP("scarecrow-consult")


def _call(question: str, lane: str, max_tokens: int, retries: int) -> dict[str, Any]:
    retries = max(1, int(retries))  # at least one attempt; retries=0 would index an empty list
    body = json.dumps({
        "model": lane,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": max_tokens,
    }).encode()
    attempts: list[dict[str, Any]] = []
    for i in range(retries):
        req = urllib.request.Request(
            PROXY, data=body,
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=300))
        except Exception as e:  # transport-level failure: record and retry
            attempts.append({"attempt": i + 1, "error": repr(e)})
            continue
        upstream = r.get("model")
        msg = r["choices"][0]["message"]
        content = msg.get("content")
        attempts.append({"attempt": i + 1, "upstream": upstream,
                         "finish": r["choices"][0].get("finish_reason"),
                         "content_len": len(content) if content else 0})
        if content and len(content.strip()) > 0:
            return {"lane": lane, "upstream_model": upstream,
                    "attempts": attempts, "answer": content}
    return {"lane": lane, "upstream_model": attempts[-1].get("upstream"),
            "attempts": attempts, "answer": None,
            "error": "all attempts returned empty content — raise max_tokens or retry"}


@mcp.tool()
def consult(question: str, lane: str = DEFAULT_LANE, max_tokens: int = 6000,
            retries: int = 4) -> str:
    """Ask a ScareCrow consultation brain a question.

    Args:
        question: the question (self-contained; the brains have no memory of prior calls).
        lane: which brain. Default bridge-chatgpt (GPT-6). Others: bridge-deepseek,
            bridge-mistral, bridge-qwen, bridge-gemini, bridge-grok, bridge-kimi,
            nvapi (nemotron), openrouter (free pool), scarecrow (round-robin).
        max_tokens: completion budget. Free reasoning upstreams need >= 6000.
        retries: retry count on empty content (the balancer rotates upstreams per call).

    Returns JSON: {lane, upstream_model, attempts, answer}. The upstream_model
    field names the brain that actually answered — always report it.
    """
    if lane not in LANES:
        return json.dumps({"error": f"unknown lane '{lane}'",
                           "valid_lanes": sorted(LANES)}, indent=1)
    return json.dumps(_call(question, lane, max_tokens, retries), indent=1)


@mcp.tool()
def list_lanes() -> str:
    """List the ScareCrow consultation lanes and what each brain is."""
    return json.dumps({"default": DEFAULT_LANE, "lanes": LANES}, indent=1)


if __name__ == "__main__":
    mcp.run()
