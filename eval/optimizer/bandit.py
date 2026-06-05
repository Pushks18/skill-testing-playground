# eval/optimizer/bandit.py
"""Thompson-sampling bandit over edit strategies for the SkillOpt optimizer.

Slice 4 component. Arms are keyed by "layer|strategy" (e.g.
"harness:base_prompt|push-tool-action"). Each arm tracks Beta(α, β) posterior
parameters initialized at Beta(1, 1) (uniform prior).

Default state path: eval/optimizer_output/bandit_state.json

Usage:
    python -m eval.optimizer.bandit --show
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
from dataclasses import dataclass, field


DEFAULT_BANDIT_PATH = pathlib.Path("eval/optimizer_output/bandit_state.json")

STRATEGIES: list[str] = [
    "push-tool-action",
    "broaden-coverage",
    "tighten-specificity",
    "add-edge-case",
    "simplify",
]

_PRIOR_ALPHA = 1.0
_PRIOR_BETA = 1.0


@dataclass
class BanditState:
    """Beta-posterior bandit state, keyed by "layer|strategy".

    Arms are initialized lazily on first access with Beta(1, 1) priors.
    """
    arms: dict[str, list[float]] = field(default_factory=dict)
    # arms[key] = [alpha, beta]

    # ── arm helpers ─────────────────────────────────────────────────────────

    def _arm_key(self, layer: str, strategy: str) -> str:
        return f"{layer}|{strategy}"

    def _ensure_arm(self, layer: str, strategy: str) -> None:
        key = self._arm_key(layer, strategy)
        if key not in self.arms:
            self.arms[key] = [_PRIOR_ALPHA, _PRIOR_BETA]

    # ── public API ──────────────────────────────────────────────────────────

    def select_strategy(
        self,
        layer: str,
        strategies: list[str],
        seed: int | None = None,
    ) -> str:
        """Thompson sampling: draw Beta(α, β) sample per arm; return argmax.

        Unseen arms are initialized with Beta(1, 1) before sampling.
        """
        rng = random.Random(seed)
        best_strategy: str | None = None
        best_sample = -1.0

        for strategy in strategies:
            self._ensure_arm(layer, strategy)
            key = self._arm_key(layer, strategy)
            alpha, beta = self.arms[key]
            sample = rng.betavariate(alpha, beta)
            if sample > best_sample:
                best_sample = sample
                best_strategy = strategy

        # Fallback (empty strategies list guard)
        if best_strategy is None:
            best_strategy = strategies[0]
        return best_strategy

    def update(self, layer: str, strategy: str, reward: bool) -> None:
        """Update Beta posterior: success → α += 1, failure → β += 1."""
        self._ensure_arm(layer, strategy)
        key = self._arm_key(layer, strategy)
        if reward:
            self.arms[key][0] += 1.0
        else:
            self.arms[key][1] += 1.0

    # ── persistence ─────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: pathlib.Path | str = DEFAULT_BANDIT_PATH) -> "BanditState":
        """Load from JSON; returns empty state (uniform priors) if file missing."""
        path = pathlib.Path(path)
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            arms = {k: list(v) for k, v in data.get("arms", {}).items()}
            return cls(arms=arms)
        except (json.JSONDecodeError, KeyError, TypeError):
            return cls()

    def save(self, path: pathlib.Path | str = DEFAULT_BANDIT_PATH) -> None:
        """Persist state to JSON."""
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"arms": self.arms}, indent=2, ensure_ascii=False)
        )

    def posterior_table(self) -> list[dict]:
        """Return rows for --show: sorted by layer|strategy, with mean and n."""
        rows = []
        for key, (alpha, beta) in sorted(self.arms.items()):
            mean = alpha / (alpha + beta)
            n = int(alpha + beta - 2)   # subtract the two prior pseudo-counts
            layer, strategy = key.split("|", 1)
            rows.append({
                "arm": key,
                "layer": layer,
                "strategy": strategy,
                "alpha": alpha,
                "beta": beta,
                "mean": round(mean, 4),
                "n": n,
            })
        return rows


# ── CLI ──────────────────────────────────────────────────────────────────────

def _show(path: pathlib.Path) -> None:
    state = BanditState.load(path)
    rows = state.posterior_table()
    if not rows:
        print("No arms recorded yet (all arms at Beta(1,1) prior).")
        return
    header = f"{'ARM':<45}  {'MEAN':>6}  {'N':>4}  {'ALPHA':>6}  {'BETA':>6}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['arm']:<45}  {row['mean']:>6.4f}  {row['n']:>4}  "
              f"{row['alpha']:>6.1f}  {row['beta']:>6.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bandit state inspector.")
    parser.add_argument(
        "--show", action="store_true",
        help="Print posterior table for all arms.",
    )
    parser.add_argument(
        "--path", default=str(DEFAULT_BANDIT_PATH),
        help=f"Path to bandit_state.json (default: {DEFAULT_BANDIT_PATH})",
    )
    args = parser.parse_args()
    if args.show:
        _show(pathlib.Path(args.path))


if __name__ == "__main__":
    main()
