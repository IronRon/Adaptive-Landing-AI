"""
Simulation harness helpers for contextual slate bandit evaluation.

This module intentionally reuses the existing bandit core logic in
``landing.bandit_utils`` and only adds synthetic data generation + reporting.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

from .bandit_utils import (
    FEATURE_NAMES,
    _conflicts_with_slate,
    make_initial_A,
    make_initial_b,
)
from .models import BanditArm, BanditArmStat, LinUCBParam


# --- Simulator tuning constants ---------------------------------------------
# Context generation
CONTEXT_NOISE_STD = 0.08          # Typical 0.03-0.15; higher => more varied synthetic users.
DEVICE_MOBILE_PROB = 0.5          # Typical 0.30-0.80; set to your real traffic mix.
VISIT_COUNT_MIN = 1               # Typical 1-2; keep >=1 to avoid zero-visit edge cases.
VISIT_COUNT_MAX = 10              # Typical 5-20; affects normalization scale only.

# Reward model
EMPTY_SLATE_P_CLICK = 0.02        # Typical 0.005-0.05; low fallback when no arms are selected.
BASE_P_CLICK = 0.05               # Typical 0.02-0.12; calibrate near real baseline CTR.
PERSONA_MATCH_BONUS = 0.20        # Typical 0.05-0.30; lift for persona-topic match.
PERSONA_MISMATCH_PENALTY = 0.05   # Typical 0.00-0.12; penalty when focus topic not matched.
BALANCED_TOPIC_BONUS = 0.03       # Typical 0.01-0.06 per matched topic for balanced persona.
BALANCED_TOPIC_BONUS_CAP = 3      # Typical 2-5; caps total balanced bonus.
INTENT_CENTER = 0.5               # Typical 0.4-0.6; midpoint where intent effect is neutral.
INTENT_WEIGHT = 0.10              # Typical 0.05-0.25; sensitivity to intent strength.
MIN_P_CLICK = 0.01                # Typical 0.001-0.05; floor to avoid zero-probability paths.
MAX_P_CLICK = 0.95                # Typical 0.80-0.99; cap to keep stochastic outcomes.


PERSONA_SPECS = {
    "price_focused": {"price": 0.85, "service": 0.35, "trust": 0.35, "location": 0.25, "contact": 0.45},
    "trust_focused": {"price": 0.35, "service": 0.40, "trust": 0.85, "location": 0.30, "contact": 0.45},
    "service_focused": {"price": 0.35, "service": 0.85, "trust": 0.40, "location": 0.30, "contact": 0.40},
    "location_focused": {"price": 0.35, "service": 0.35, "trust": 0.40, "location": 0.85, "contact": 0.40},
    "contact_focused": {"price": 0.30, "service": 0.35, "trust": 0.45, "location": 0.35, "contact": 0.85},
    "balanced": {"price": 0.55, "service": 0.55, "trust": 0.55, "location": 0.55, "contact": 0.55},
}


PERSONA_KEYWORDS = {
    "price": ("pricing", "price", "plan"),
    "trust": ("testimonials", "faq", "trust", "review"),
    "service": ("services", "service"),
    "location": ("locations", "location"),
    "contact": ("contact", "cta"),
}


@dataclass
class SimRound:
    round_idx: int
    policy: str
    persona: str
    device: str
    chosen_arm_ids: List[str]
    p_click: float
    reward: int


def clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def choose_persona(rng: random.Random, personas: Sequence[str] | None = None) -> str:
    names = list(personas) if personas else list(PERSONA_SPECS.keys())
    return rng.choice(names)


def build_synthetic_context(persona: str, rng: random.Random, noise_std: float = CONTEXT_NOISE_STD) -> Tuple[Dict[str, float], List[float]]:
    """
    Build synthetic intent + device context and convert it into the same feature
    vector layout expected by the bandit core (`FEATURE_NAMES`).
    """
    base = PERSONA_SPECS[persona]
    noisy_scores = {}
    for key, base_value in base.items():
        noisy_scores[key] = clip01(base_value + rng.gauss(0.0, noise_std))

    device = "mobile" if rng.random() < DEVICE_MOBILE_PROB else "desktop"
    is_mobile = 1.0 if device == "mobile" else 0.0

    visit_count = rng.randint(VISIT_COUNT_MIN, VISIT_COUNT_MAX)
    visit_number_norm = min(visit_count, VISIT_COUNT_MAX) / float(VISIT_COUNT_MAX)

    context = {
        "persona": persona,
        "device": device,
        "is_mobile": is_mobile,
        "price": noisy_scores["price"],
        "service": noisy_scores["service"],
        "trust": noisy_scores["trust"],
        "location": noisy_scores["location"],
        "contact": noisy_scores["contact"],
        "visit_count": float(visit_count),
        "visit_number_norm": visit_number_norm,
    }

    feature_map = {
        "is_mobile": context["is_mobile"],
        "price_score": context["price"],
        "service_score": context["service"],
        "trust_score": context["trust"],
        "location_score": context["location"],
        "contact_score": context["contact"],
        "visit_number_norm": context["visit_number_norm"],
        "bias": 1.0,
    }
    feature_vector = [float(feature_map.get(name, 0.0)) for name in FEATURE_NAMES]
    return context, feature_vector


def _arm_topics(arm: BanditArm) -> set[str]:
    """Infer arm topical tags from affected_sections and page_config metadata."""
    tokens = set()

    for section in (arm.affected_sections or []):
        if section:
            tokens.add(str(section).lower())

    cfg = arm.page_config or {}
    for section in cfg.get("compact", []):
        tokens.add(str(section).lower())
    for section in cfg.get("hide", []):
        tokens.add(str(section).lower())
    if cfg.get("promote"):
        tokens.add(str(cfg["promote"]).lower())
    for key in (cfg.get("variants") or {}).keys():
        tokens.add(str(key).lower())

    return tokens


def arm_matches_topic(arm: BanditArm, topic: str) -> bool:
    keywords = PERSONA_KEYWORDS[topic]
    tokens = _arm_topics(arm)
    # Loose substring matching keeps this robust to arm naming differences.
    return any(any(keyword in token for keyword in keywords) for token in tokens)


def simulate_reward(
    persona: str,
    chosen_arms: Sequence[BanditArm],
    context: Dict[str, float],
    rng: random.Random,
) -> Tuple[int, float]:
    """
    Return binary reward and click probability from a simple persona-arm match rule.
    """
    if not chosen_arms:
        # Very low fallback CTR when no treatment is shown.
        p_click = EMPTY_SLATE_P_CLICK
        return (1 if rng.random() < p_click else 0), p_click

    base_rate = BASE_P_CLICK
    p_click = base_rate

    focus_topic = persona.replace("_focused", "") if persona.endswith("_focused") else None
    if focus_topic and focus_topic in PERSONA_KEYWORDS:
        # Focused personas get rewarded for at least one matching arm.
        if any(arm_matches_topic(arm, focus_topic) for arm in chosen_arms):
            p_click += PERSONA_MATCH_BONUS
        else:
            p_click -= PERSONA_MISMATCH_PENALTY

    if persona == "balanced":
        # Balanced users benefit from coverage across multiple topics, up to a cap.
        matched_topics = sum(
            1 for topic in ("price", "trust", "service", "location", "contact")
            if any(arm_matches_topic(arm, topic) for arm in chosen_arms)
        )
        p_click += BALANCED_TOPIC_BONUS * min(BALANCED_TOPIC_BONUS_CAP, matched_topics)

    # Light dependence on synthetic intent + device.
    top_intent = max(context["price"], context["trust"], context["service"], context["location"], context["contact"])
    p_click += INTENT_WEIGHT * (top_intent - INTENT_CENTER)

    p_click = float(max(MIN_P_CLICK, min(MAX_P_CLICK, p_click)))
    reward = 1 if rng.random() < p_click else 0
    return reward, p_click


def random_non_conflicting_slate(
    arms: Sequence[BanditArm],
    k: int,
    rng: random.Random,
) -> List[BanditArm]:
    """Pick up to K random non-conflicting arms (excluding control arm)."""
    candidates = [arm for arm in arms if arm.arm_id != "no_change"]
    shuffled = list(candidates)
    rng.shuffle(shuffled)

    chosen = []
    for arm in shuffled:
        if len(chosen) >= k:
            break
        # Reuse production conflict rules so random baseline is still valid.
        if not _conflicts_with_slate(arm, chosen):
            chosen.append(arm)
    return chosen


def no_change_slate(arms: Sequence[BanditArm]) -> List[BanditArm]:
    for arm in arms:
        if arm.arm_id == "no_change":
            return [arm]
    return []


def reset_bandit_params() -> None:
    """Reset learned model state in DB so simulation starts from scratch."""
    LinUCBParam.objects.all().delete()
    BanditArmStat.objects.all().delete()

    for arm in BanditArm.objects.filter(is_active=True):
        LinUCBParam.objects.create(
            arm=arm,
            A_matrix=make_initial_A(),
            b_vector=make_initial_b(),
            n=0,
        )


def moving_average(values: Sequence[float], window: int = 200) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return arr
    if window <= 1:
        return arr

    # Keep output length equal to input length, even when window > len(arr).
    effective_window = min(int(window), int(arr.size))
    # Prefix sums let us compute all sliding-window means in O(n).
    csum = np.cumsum(np.insert(arr, 0, 0.0))
    raw = (csum[effective_window:] - csum[:-effective_window]) / float(effective_window)

    if effective_window == arr.size:
        return np.full(arr.size, float(raw[0]))

    pad_left = effective_window // 2
    pad_right = arr.size - raw.size - pad_left
    return np.pad(raw, (pad_left, pad_right), mode="edge")


def cumulative_average(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return arr
    return np.cumsum(arr) / np.arange(1, arr.size + 1)


def save_rounds_csv(rows: Iterable[SimRound], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["round", "policy", "persona", "device", "chosen_arm_ids", "p_click", "reward"])
        for row in rows:
            writer.writerow([
                row.round_idx,
                row.policy,
                row.persona,
                row.device,
                "|".join(row.chosen_arm_ids),
                f"{row.p_click:.6f}",
                row.reward,
            ])


def summarize(rows: Sequence[SimRound]) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}

    policies = sorted({row.policy for row in rows})
    for policy in policies:
        # Compute metrics independently per policy (bandit/random/no_change).
        policy_rows = [r for r in rows if r.policy == policy]
        if not policy_rows:
            continue

        overall_ctr = float(np.mean([r.reward for r in policy_rows]))
        summary[policy] = {"overall_ctr": overall_ctr, "n": float(len(policy_rows))}

        personas = sorted({r.persona for r in policy_rows})
        for persona in personas:
            persona_rows = [r for r in policy_rows if r.persona == persona]
            summary[policy][f"persona:{persona}"] = float(np.mean([r.reward for r in persona_rows]))

        devices = sorted({r.device for r in policy_rows})
        for device in devices:
            device_rows = [r for r in policy_rows if r.device == device]
            summary[policy][f"device:{device}"] = float(np.mean([r.reward for r in device_rows]))

    return summary
