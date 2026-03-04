from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field

from spice_war.game.simulator import simulate_war
from spice_war.models.configurable import ConfigurableModel
from spice_war.utils.data_structures import Alliance, EventConfig


@dataclass
class MonteCarloResult:
    num_iterations: int
    base_seed: int
    tier_counts: dict[str, Counter[int]] = field(default_factory=dict)
    spice_totals: dict[str, list[int]] = field(default_factory=dict)
    per_iteration: list[dict] = field(default_factory=list)
    targeting_counts: dict[str, dict[str, Counter[str]]] = field(default_factory=dict)

    def tier_distribution(self, alliance_id: str) -> dict[int, float]:
        counts = self.tier_counts[alliance_id]
        return {tier: counts[tier] / self.num_iterations for tier in range(1, 6)}

    def spice_stats(self, alliance_id: str) -> dict[str, int]:
        values = sorted(self.spice_totals[alliance_id])
        n = len(values)
        return {
            "mean": round(statistics.mean(values)),
            "median": round(statistics.median(values)),
            "min": values[0],
            "max": values[-1],
            "p25": values[n // 4],
            "p75": values[3 * n // 4],
        }

    def rank_summary(self) -> dict[str, dict[int, float]]:
        return {aid: self.tier_distribution(aid) for aid in self.tier_counts}

    def targeting_matrix(self) -> dict[str, dict[str, dict[str, float]]]:
        matrix = {}
        for event_num, attackers in self.targeting_counts.items():
            matrix[event_num] = {}
            for attacker_id, defender_counts in attackers.items():
                matrix[event_num][attacker_id] = {
                    def_id: count / self.num_iterations
                    for def_id, count in defender_counts.items()
                }
        return matrix

    def most_likely_tier(self, alliance_id: str) -> int:
        counts = self.tier_counts[alliance_id]
        return max(range(1, 6), key=lambda t: counts[t])


def run_monte_carlo(
    alliances: list[Alliance],
    event_schedule: list[EventConfig],
    model_config: dict,
    num_iterations: int,
    base_seed: int = 0,
) -> MonteCarloResult:
    result = MonteCarloResult(
        num_iterations=num_iterations,
        base_seed=base_seed,
    )

    alliance_ids = [a.alliance_id for a in alliances]
    for aid in alliance_ids:
        result.tier_counts[aid] = Counter()
        result.spice_totals[aid] = []

    for i in range(num_iterations):
        iter_config = dict(model_config)
        iter_config["random_seed"] = base_seed + i

        model = ConfigurableModel(iter_config, alliances)
        war_result = simulate_war(alliances, event_schedule, model)

        for event in war_result["event_history"]:
            event_num = str(event["event_number"])
            if event_num not in result.targeting_counts:
                result.targeting_counts[event_num] = {}
            for attacker_id, defender_id in event["targeting"].items():
                if attacker_id not in result.targeting_counts[event_num]:
                    result.targeting_counts[event_num][attacker_id] = Counter()
                result.targeting_counts[event_num][attacker_id][defender_id] += 1

        for aid in alliance_ids:
            result.spice_totals[aid].append(war_result["final_spice"][aid])
            result.tier_counts[aid][war_result["rankings"][aid]] += 1

        result.per_iteration.append({
            "seed": base_seed + i,
            "final_spice": dict(war_result["final_spice"]),
            "rankings": dict(war_result["rankings"]),
        })

    return result
