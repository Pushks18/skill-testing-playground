# eval/cost.py
"""Token cost calculator — prices per 1M tokens via OpenRouter (USD)."""
from __future__ import annotations

# Prices in USD per 1M tokens (input, output)
# Source: openrouter.ai/models — update when pricing changes
_PRICING: dict[str, tuple[float, float]] = {
    # OpenRouter model strings
    "google/gemini-2.5-flash":          (0.15,  0.60),
    "google/gemini-2.5-pro":            (1.25,  10.00),
    "anthropic/claude-haiku-4-5":       (0.80,  4.00),
    "anthropic/claude-sonnet-4-6":      (3.00,  15.00),
    "openai/gpt-4.1-mini":              (0.40,  1.60),
    "openai/gpt-4.1":                   (2.00,  8.00),
    "meta-llama/llama-3.1-8b-instruct": (0.06,  0.06),
    # OpenAI direct model strings
    "gpt-4o":                           (2.50,  10.00),
    "gpt-4o-mini":                      (0.15,   0.60),
    "gpt-4.1":                          (2.00,   8.00),
    "gpt-4.1-mini":                     (0.40,   1.60),
    "o1-mini":                          (3.00,  12.00),
    "o3-mini":                          (1.10,   4.40),
}

_DEFAULT = (1.00, 3.00)   # fallback if model unknown


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return cost in USD for one LLM call."""
    in_price, out_price = _PRICING.get(model, _DEFAULT)
    return round(
        (input_tokens * in_price + output_tokens * out_price) / 1_000_000,
        6,
    )


def format_cost(cost_usd: float) -> str:
    if cost_usd < 0.001:
        return f"${cost_usd * 1000:.4f}m"   # millidollars
    return f"${cost_usd:.4f}"


def cost_summary(results) -> dict:
    """Aggregate cost + token metrics across a list of EvalResults."""
    total_cost   = sum(r.cost_usd     for r in results)
    total_in     = sum(r.input_tokens  for r in results)
    total_out    = sum(r.output_tokens for r in results)
    total_lat    = sum(r.latency_ms    for r in results)
    n = len(results) or 1
    return {
        "total_cost_usd":       round(total_cost, 6),
        "avg_cost_usd":         round(total_cost / n, 6),
        "total_input_tokens":   total_in,
        "total_output_tokens":  total_out,
        "avg_latency_ms":       round(total_lat / n),
        "p95_latency_ms":       _p95([r.latency_ms for r in results]),
    }


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = max(0, int(len(s) * 0.95) - 1)
    return s[idx]
