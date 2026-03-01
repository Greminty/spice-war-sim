from __future__ import annotations

import csv
import io

from spice_war.game.monte_carlo import run_monte_carlo as run_monte_carlo_impl
from spice_war.game.simulator import simulate_war
from spice_war.models.configurable import ConfigurableModel
from spice_war.utils.data_structures import Alliance, EventConfig
from spice_war.utils.validation import ValidationError, _check_model_references

_ALLOWED_MODEL_KEYS = {
    "random_seed",
    "battle_outcome_matrix",
    "event_targets",
    "event_reinforcements",
    "damage_weights",
    "targeting_strategy",
    "default_targets",
    "faction_targeting_strategy",
}


def _validate_state_structure(state_dict: dict) -> None:
    if not isinstance(state_dict, dict):
        raise ValidationError("State must be a JSON object")
    if "alliances" not in state_dict:
        raise ValidationError("State must contain 'alliances'")
    if "event_schedule" not in state_dict:
        raise ValidationError("State must contain 'event_schedule'")
    if not state_dict["alliances"]:
        raise ValidationError("State must contain at least one alliance")
    if not state_dict["event_schedule"]:
        raise ValidationError("State must contain at least one event")

    factions = {a["faction"] for a in state_dict["alliances"] if "faction" in a}
    if len(factions) != 2:
        raise ValidationError(
            f"State must contain exactly 2 factions, found {len(factions)}: "
            f"{sorted(factions)}"
        )

    for i, event in enumerate(state_dict["event_schedule"]):
        if "attacker_faction" in event and event["attacker_faction"] not in factions:
            raise ValidationError(
                f"Event #{i + 1}: attacker_faction '{event['attacker_faction']}' "
                f"is not one of the state's factions: {sorted(factions)}"
            )

    ids = [a.get("alliance_id") for a in state_dict["alliances"]]
    dupes = [aid for aid in ids if ids.count(aid) > 1]
    if dupes:
        raise ValidationError(
            f"Duplicate alliance_id(s): {sorted(set(dupes))}"
        )


def _build_alliances(state_dict: dict) -> list[Alliance]:
    alliances = []
    for i, raw in enumerate(state_dict.get("alliances", [])):
        required = ["alliance_id", "faction", "power", "starting_spice", "daily_rate"]
        missing = [k for k in required if k not in raw]
        if missing:
            raise ValidationError(
                f"Alliance #{i + 1}: missing required fields: {missing}"
            )
        if raw["alliance_id"] == "*":
            raise ValidationError(
                f"Alliance #{i + 1}: '*' is reserved and cannot be used "
                f"as an alliance_id"
            )
        alliances.append(
            Alliance(
                alliance_id=raw["alliance_id"],
                faction=raw["faction"],
                power=raw["power"],
                starting_spice=raw["starting_spice"],
                daily_spice_rate=raw["daily_rate"],
                name=raw.get("name"),
                server=raw.get("server"),
            )
        )
    return alliances


def _build_schedule(state_dict: dict) -> list[EventConfig]:
    schedule = []
    for i, raw in enumerate(state_dict.get("event_schedule", [])):
        required = ["attacker_faction", "day", "days_before"]
        missing = [k for k in required if k not in raw]
        if missing:
            raise ValidationError(
                f"Event #{i + 1}: missing required fields: {missing}"
            )
        day = raw["day"].lower()
        if day not in ("wednesday", "saturday"):
            raise ValidationError(
                f"Event #{i + 1}: day must be 'wednesday' or 'saturday', "
                f"got '{raw['day']}'"
            )
        schedule.append(
            EventConfig(
                attacker_faction=raw["attacker_faction"],
                day=day,
                days_before=raw["days_before"],
            )
        )
    return schedule


def _validate_model_dict(model_dict: dict, alliances: list[Alliance]) -> None:
    if not isinstance(model_dict, dict):
        raise ValidationError("Model config must be a JSON object")

    unknown = set(model_dict.keys()) - _ALLOWED_MODEL_KEYS
    if unknown:
        raise ValidationError(f"Unknown model config keys: {sorted(unknown)}")

    alliance_ids = {a.alliance_id for a in alliances}
    faction_ids = {a.faction for a in alliances}
    _check_model_references(model_dict, alliance_ids, faction_ids)


def get_default_state() -> dict:
    return {
        "alliances": [
            {
                "alliance_id": "Alpha",
                "faction": "Sun",
                "power": 15.0,
                "starting_spice": 2_000_000,
                "daily_rate": 50_000,
            },
            {
                "alliance_id": "Bravo",
                "faction": "Sun",
                "power": 10.0,
                "starting_spice": 1_500_000,
                "daily_rate": 40_000,
            },
            {
                "alliance_id": "Charlie",
                "faction": "Moon",
                "power": 12.0,
                "starting_spice": 1_800_000,
                "daily_rate": 45_000,
            },
            {
                "alliance_id": "Delta",
                "faction": "Moon",
                "power": 8.0,
                "starting_spice": 1_200_000,
                "daily_rate": 35_000,
            },
        ],
        "event_schedule": [
            {"attacker_faction": "Sun", "day": "wednesday", "days_before": 21},
            {"attacker_faction": "Moon", "day": "saturday", "days_before": 18},
            {"attacker_faction": "Sun", "day": "wednesday", "days_before": 14},
            {"attacker_faction": "Moon", "day": "saturday", "days_before": 11},
        ],
    }


def get_default_model_config() -> dict:
    return {}


def validate_state(state_dict: dict) -> dict:
    try:
        _validate_state_structure(state_dict)
        alliances = _build_alliances(state_dict)
        schedule = _build_schedule(state_dict)
        return {
            "ok": True,
            "alliances": [
                {
                    "alliance_id": a.alliance_id,
                    "faction": a.faction,
                    "power": a.power,
                    "starting_spice": a.starting_spice,
                    "daily_rate": a.daily_spice_rate,
                }
                for a in alliances
            ],
            "event_schedule": [
                {
                    "event_number": i + 1,
                    "attacker_faction": e.attacker_faction,
                    "day": e.day,
                    "days_before": e.days_before,
                }
                for i, e in enumerate(schedule)
            ],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def validate_model_config(model_dict: dict, state_dict: dict) -> dict:
    try:
        alliances = _build_alliances(state_dict)
        _validate_model_dict(model_dict, alliances)
        return {"ok": True, "config": model_dict}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_single(
    state_dict: dict, model_dict: dict, seed: int | None = None
) -> dict:
    try:
        _validate_state_structure(state_dict)
        alliances = _build_alliances(state_dict)
        schedule = _build_schedule(state_dict)
        _validate_model_dict(model_dict, alliances)

        config = dict(model_dict)
        if seed is not None:
            config["random_seed"] = seed
        elif "random_seed" not in config:
            config["random_seed"] = 0

        model = ConfigurableModel(config, alliances)
        result = simulate_war(alliances, schedule, model)

        return {
            "ok": True,
            "seed": config["random_seed"],
            "final_spice": result["final_spice"],
            "rankings": result["rankings"],
            "event_history": result["event_history"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_monte_carlo(
    state_dict: dict,
    model_dict: dict,
    num_iterations: int = 1000,
    base_seed: int = 0,
) -> dict:
    try:
        _validate_state_structure(state_dict)
        alliances = _build_alliances(state_dict)
        schedule = _build_schedule(state_dict)
        _validate_model_dict(model_dict, alliances)

        result = run_monte_carlo_impl(
            alliances, schedule, model_dict,
            num_iterations=num_iterations,
            base_seed=base_seed,
        )

        return {
            "ok": True,
            "num_iterations": result.num_iterations,
            "base_seed": result.base_seed,
            "tier_distribution": {
                aid: {
                    str(tier): frac
                    for tier, frac in result.tier_distribution(aid).items()
                }
                for aid in result.tier_counts
            },
            "spice_stats": {
                aid: result.spice_stats(aid)
                for aid in result.tier_counts
            },
            "raw_results": result.per_iteration,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def import_csv(csv_text: str) -> dict:
    try:
        from spice_war.sheets.importer import import_from_csv

        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        config = import_from_csv(rows)
        return {"ok": True, "config": config}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def generate_template_csv(state_dict: dict, top_n: int = 6) -> dict:
    try:
        from spice_war.sheets.template import generate_template

        alliances = _build_alliances(state_dict)
        schedule = _build_schedule(state_dict)
        rows = generate_template(alliances, schedule, top_n=top_n)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return {"ok": True, "csv": output.getvalue()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
