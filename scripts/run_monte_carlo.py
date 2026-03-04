#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from spice_war.game.monte_carlo import MonteCarloResult, run_monte_carlo
from spice_war.utils.validation import ValidationError, load_model_config, load_state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Monte Carlo simulation")
    parser.add_argument("state_file", help="Path to initial state JSON")
    parser.add_argument("model_file", nargs="?", default=None, help="Path to model config JSON")
    parser.add_argument("-n", "--num-iterations", type=int, default=1000, help="Number of simulation runs")
    parser.add_argument("--base-seed", type=int, default=0, help="Starting seed")
    parser.add_argument("--output", metavar="PATH", help="Write JSON results to file")
    parser.add_argument("--quiet", action="store_true", help="Suppress summary table")
    parser.add_argument(
        "--alliance", action="append", dest="alliances", default=None,
        help="Show only this alliance in output (repeatable)"
    )
    args = parser.parse_args(argv)

    try:
        alliances, schedule = load_state(args.state_file)
        alliance_ids = {a.alliance_id for a in alliances}
        model_config = load_model_config(args.model_file, alliance_ids)
    except ValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    result = run_monte_carlo(
        alliances, schedule, model_config,
        num_iterations=args.num_iterations,
        base_seed=args.base_seed,
    )

    # Derive display_aids for filtering
    alliance_id_set = {a.alliance_id for a in alliances}
    if args.alliances:
        display_aids = [aid for aid in args.alliances if aid in alliance_id_set]
        unknown = [aid for aid in args.alliances if aid not in alliance_id_set]
        for aid in unknown:
            print(f"Warning: unknown alliance '{aid}'", file=sys.stderr)
    else:
        display_aids = None

    if not args.quiet:
        _print_summary(alliances, schedule, result, display_aids)

    if args.output:
        _write_json(args.output, result, display_aids)

    return 0


def _print_summary(
    alliances: list,
    schedule: list,
    result: MonteCarloResult,
    display_aids: list[str] | None = None,
) -> None:
    n = result.num_iterations
    end_seed = result.base_seed + n - 1
    print(f"Monte Carlo Simulation — {n} iterations (seeds {result.base_seed}–{end_seed})")
    print()

    # Sort alliances by mean spice descending
    sorted_aids = sorted(
        [a.alliance_id for a in alliances],
        key=lambda aid: result.spice_stats(aid)["mean"],
        reverse=True,
    )
    if display_aids is not None:
        display_set = set(display_aids)
        sorted_aids = [aid for aid in sorted_aids if aid in display_set]
    if not sorted_aids:
        return
    name_width = max(len(aid) for aid in sorted_aids)

    # Tier distribution table
    print("Tier Distribution (% of iterations):")
    print(f"{'':>{name_width}}    Tier 1    Tier 2    Tier 3    Tier 4    Tier 5")
    for aid in sorted_aids:
        dist = result.tier_distribution(aid)
        parts = [f"{dist[t] * 100:>7.1f}%" for t in range(1, 6)]
        print(f"{aid:>{name_width}}  {'  '.join(parts)}")
    print()

    # Spice summary table
    print("Spice Summary:")
    print(f"{'':>{name_width}}        Mean      Median         Min         Max")
    for aid in sorted_aids:
        stats = result.spice_stats(aid)
        print(
            f"{aid:>{name_width}}"
            f"  {stats['mean']:>11,}"
            f"  {stats['median']:>11,}"
            f"  {stats['min']:>11,}"
            f"  {stats['max']:>11,}"
        )

    _print_targeting_matrices(alliances, schedule, result, display_aids)


def _print_targeting_matrices(
    alliances: list,
    schedule: list,
    result: MonteCarloResult,
    display_aids: list[str] | None = None,
) -> None:
    matrix = result.targeting_matrix()
    if not matrix:
        return

    power_map = {a.alliance_id: a.power for a in alliances}
    display_set = set(display_aids) if display_aids else None

    for event_num in sorted(matrix, key=int):
        event_data = matrix[event_num]
        idx = int(event_num) - 1
        event_cfg = schedule[idx]

        attackers = set(event_data.keys())
        defenders = set()
        for targets in event_data.values():
            defenders.update(targets.keys())

        if display_set:
            attackers &= display_set
            defenders &= display_set
        if not attackers or not defenders:
            continue

        sorted_attackers = sorted(attackers, key=lambda a: power_map.get(a, 0), reverse=True)
        sorted_defenders = sorted(defenders, key=lambda d: power_map.get(d, 0), reverse=True)

        print()
        print(f"Event {event_num} — {event_cfg.attacker_faction} attacks ({event_cfg.day})")

        name_w = max(len(a) for a in sorted_attackers)
        col_w = max(max(len(d) for d in sorted_defenders), 6)

        header = f"{'':>{name_w}}  " + "  ".join(f"{d:>{col_w}}" for d in sorted_defenders)
        print(header)

        for att in sorted_attackers:
            cells = []
            for def_ in sorted_defenders:
                frac = event_data.get(att, {}).get(def_, 0)
                cell = f"{frac * 100:.1f}%"
                cells.append(f"{cell:>{col_w}}")
            print(f"{att:>{name_w}}  {'  '.join(cells)}")


def _filter_targeting_matrix(
    matrix: dict, aid_set: set[str],
) -> dict:
    filtered = {}
    for event_num, attackers in matrix.items():
        event_filtered = {}
        for att_id, defenders in attackers.items():
            if att_id not in aid_set:
                continue
            def_filtered = {d: f for d, f in defenders.items() if d in aid_set}
            if def_filtered:
                event_filtered[att_id] = def_filtered
        if event_filtered:
            filtered[event_num] = event_filtered
    return filtered


def _write_json(
    path: str,
    result: MonteCarloResult,
    display_aids: list[str] | None = None,
) -> None:
    aid_set = set(display_aids) if display_aids else set(result.tier_counts)

    data = {
        "num_iterations": result.num_iterations,
        "base_seed": result.base_seed,
        "tier_distribution": {
            aid: {str(tier): frac for tier, frac in dist.items()}
            for aid, dist in result.rank_summary().items()
            if aid in aid_set
        },
        "spice_stats": {
            aid: result.spice_stats(aid)
            for aid in result.tier_counts
            if aid in aid_set
        },
        "targeting_matrix": _filter_targeting_matrix(result.targeting_matrix(), aid_set),
        "raw_results": [
            {
                "seed": entry["seed"],
                "final_spice": {
                    k: v for k, v in entry["final_spice"].items()
                    if k in aid_set
                },
                "rankings": {
                    k: v for k, v in entry["rankings"].items()
                    if k in aid_set
                },
            }
            for entry in result.per_iteration
        ],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
