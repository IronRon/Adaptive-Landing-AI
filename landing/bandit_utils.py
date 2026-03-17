"""
Bandit utility functions — Combinational Contextual Multi-Armed Bandit.

build_context      – turn a visitor into a list of 8 numbers (the feature vector)
choose_arm         – (legacy) single-arm ε-greedy selection
choose_slate       – pick K non-conflicting arms per visit (slate bandit)
merge_page_configs – combine page_config dicts from a slate into one
update_stats       – learn from the result of a session (adjust weights)

How it works (plain English)
----------------------------
Instead of putting visitors into rigid buckets like "desktop_price",
each visitor is described by a list of 8 numbers — their feature vector.
Nothing is thrown away; all the continuous scores are kept as-is.

Each arm learns a set of **weights** — one weight per feature. To predict
whether an arm will work for a visitor, multiply each feature by its
weight and add them up:

    predicted_reward = sum(feature_i × weight_i  for each feature)

For returning visitors (visit_number >= 2) the bandit picks a SLATE of
K=3 non-conflicting arms, merges their page_configs, and sends the
combined config to the frontend.

At session end the reward (CTA clicked = 1, else 0) is applied only to
arms whose affected sections were actually *observed* by the user
(section_view / section_dwell events).

Feature vector (d=8)
--------------------
    [is_mobile, price_score, service_score, trust_score,
     location_score, contact_score, visit_number_norm, bias]
"""

import logging
import random

import numpy as np

from .models import BanditArm, LinUCBParam, Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EPSILON = 0.10              # 10% of the time, pick a random arm (explore)
MIN_PULLS_PER_ARM = 2       # try every arm at least 2 times before trusting predictions
LAMBDA_REG = 1.0             # safety factor for A_matrix starting values (keeps early predictions conservative)

# Feature vector layout
FEATURE_NAMES = [
    "is_mobile",             # 0 or 1
    "price_score",           # 0..1 from last session
    "service_score",         # 0..1
    "trust_score",           # 0..1
    "location_score",        # 0..1
    "contact_score",         # 0..1
    "visit_number_norm",     # min(visit_count, 10) / 10
    "bias",                  # always 1.0
]
FEATURE_DIM = len(FEATURE_NAMES)   # 8


# ---------------------------------------------------------------------------
# Numpy helpers — converting to/from JSON-safe lists for database storage
# ---------------------------------------------------------------------------

def make_initial_A():
    """Return the starting A_matrix as a JSON-safe nested list.

    np.eye(d) creates an 8×8 identity matrix (1s on diagonal, 0s elsewhere).
    Multiplied by LAMBDA_REG (1.0) as a safety net for early predictions.
    .tolist() converts the numpy array to plain Python lists for JSONField.
    """
    return (np.eye(FEATURE_DIM) * LAMBDA_REG).tolist()


def make_initial_b():
    """Return the starting b_vector as a JSON-safe list.

    np.zeros(d) creates a list of 8 zeros — "no rewards seen yet."
    .tolist() converts to plain Python list for JSONField.
    """
    return np.zeros(FEATURE_DIM).tolist()


def _predict(A_list, b_list, x_list):
    """
    Predict reward for a visitor (context vector x).

    1. np.array() converts the stored JSON lists back into numpy arrays.
    2. np.linalg.solve(A, b) computes weights = A⁻¹ × b
       ("what worked" ÷ "what I've seen").
    3. weights @ x multiplies each feature by its weight and adds up
       → a single predicted reward number.
    """
    A = np.array(A_list)
    b = np.array(b_list)
    x = np.array(x_list)
    weights = np.linalg.solve(A, b)
    return float(weights @ x)


# ---------------------------------------------------------------------------
# 1) build_context
# ---------------------------------------------------------------------------

def build_context(visitor, request):
    """
    Extract context features from the visitor and request.

    Returns
    -------
    context_dict : dict
        Human-readable snapshot (for logging / auditing in BanditDecision).
    feature_vector : list[float]
        Numeric vector of length FEATURE_DIM used by the linear model.
    """
    # --- device type -------------------------------------------------------
    ua = request.META.get("HTTP_USER_AGENT", "").lower()
    mobile_keywords = (
        "mobile", "android", "iphone", "ipod", "ipad",
        "opera mini", "iemobile",
    )
    is_mobile = 1.0 if any(kw in ua for kw in mobile_keywords) else 0.0

    # --- intent scores from the most recent ended session ------------------
    last_session = (
        Session.objects
        .filter(visitor=visitor, ended_at__isnull=False)
        .order_by("-ended_at")
        .first()
    )

    if last_session:
        price    = last_session.price_intent_score or 0.0
        service  = last_session.service_intent_score or 0.0
        trust    = last_session.trust_intent_score or 0.0
        location = last_session.location_intent_score or 0.0
        contact  = last_session.contact_intent_score or 0.0
    else:
        price = service = trust = location = contact = 0.0

    # --- visit count (normalised to 0–1) -----------------------------------
    visit_count = visitor.sessions.count()
    visit_norm = min(visit_count, 10) / 10.0

    # --- assemble feature vector -------------------------------------------
    feature_vector = [
        is_mobile,
        price,
        service,
        trust,
        location,
        contact,
        visit_norm,
        1.0,     # bias term — lets the model learn a constant offset
    ]

    context_dict = {
        "is_mobile": bool(is_mobile),
        "price_score": price,
        "service_score": service,
        "trust_score": trust,
        "location_score": location,
        "contact_score": contact,
        "visit_count": visit_count,
        "visit_number_norm": visit_norm,
    }

    return context_dict, feature_vector


# ---------------------------------------------------------------------------
# 2) choose_arm
# ---------------------------------------------------------------------------

def choose_arm(feature_vector, epsilon=EPSILON):
    """
    ε-greedy arm selection using linear reward prediction.

    Warmup
        If any active arm has fewer than MIN_PULLS_PER_ARM observations,
        pick a random under-pulled arm (forced exploration).

    Explore (probability ε)
        Pick a uniformly random arm.

    Exploit (probability 1 − ε)
        For each arm compute  predicted_reward = dot(x, θ_arm)
        and pick the arm with the highest value.

    Returns ``(arm, explored_flag, predicted_score)``.
    ``predicted_score`` is the model's predicted reward for the chosen arm,
    or ``None`` during warmup / exploration.
    """
    arms = list(BanditArm.objects.filter(is_active=True))
    if not arms:
        raise ValueError("No active BanditArm rows — run seed_bandit_arms first.")

    # Ensure every arm has a LinUCBParam row (auto-initialise if missing)
    params = {}
    under_pulled = []
    for arm in arms:
        param, _created = LinUCBParam.objects.get_or_create(
            arm=arm,
            defaults={
                "A_matrix": make_initial_A(),
                "b_vector": make_initial_b(),
            },
        )
        params[arm.pk] = param
        if param.n < MIN_PULLS_PER_ARM:
            under_pulled.append(arm)

    # --- warmup: force-explore under-pulled arms ---------------------------
    if under_pulled:
        chosen = random.choice(under_pulled)
        logger.info("Bandit warmup: arm=%s (n=%d)", chosen.arm_id, params[chosen.pk].n)
        return chosen, True, None

    # --- ε-greedy ----------------------------------------------------------
    if random.random() < epsilon:
        chosen = random.choice(arms)
        logger.info("Bandit explore (ε=%.2f): arm=%s", epsilon, chosen.arm_id)
        return chosen, True, None

    # Exploit — pick arm with highest predicted reward
    best_arm = None
    best_score = -float("inf")
    for arm in arms:
        param = params[arm.pk]
        score = _predict(param.A_matrix, param.b_vector, feature_vector)
        if score > best_score:
            best_score = score
            best_arm = arm

    logger.info("Bandit exploit: arm=%s predicted=%.4f", best_arm.arm_id, best_score)
    return best_arm, False, best_score


# ---------------------------------------------------------------------------
# 3) update_stats
# ---------------------------------------------------------------------------

def update_stats(arm, feature_vector, reward):
    """
    Learn from a completed session — update this arm's stored parameters.

    A_matrix ("what I've seen"):
        Add this visitor's feature combinations so the model remembers
        what kind of visitors it has been shown to. This is done by
        multiplying the feature vector by itself to get an 8×8 grid
        and adding it to A_matrix.

    b_vector ("what worked"):
        Add this visitor's features × reward. If the visitor clicked
        (reward=1), their features get added in full. If they didn't
        click (reward=0), nothing changes — only successes contribute.

    Next time we need weights:  weights = A_matrix⁻¹ × b_vector
    i.e. "what worked" divided by "what I've seen" = best prediction.
    """
    param, _ = LinUCBParam.objects.get_or_create(
        arm=arm,
        defaults={
            "A_matrix": make_initial_A(),
            "b_vector": make_initial_b(),
        },
    )

    # Convert stored lists into numpy arrays for easy math
    x = np.array(feature_vector)
    A = np.array(param.A_matrix)
    b = np.array(param.b_vector)

    # "What I've seen" — np.outer(x, x) gives the 8×8 feature combination grid
    A = A + np.outer(x, x)

    # "What worked" — features × reward (only changes if reward > 0)
    b = b + reward * x

    # Convert back to plain lists for JSONField storage
    param.A_matrix = A.tolist()
    param.b_vector = b.tolist()
    param.n += 1
    param.save()

    logger.info(
        "Bandit update: arm=%s reward=%.1f n=%d",
        arm.arm_id, reward, param.n,
    )


# ---------------------------------------------------------------------------
# 4) Conflict detection for slate selection
# ---------------------------------------------------------------------------

def _has_conflict(arm_a, arm_b):
    """
    Check whether two arms conflict and cannot coexist in the same slate.

    Conflict rules
    --------------
    1. Same arm (duplicate).
    2. Both set the same key in page_config.variants.
    3. Both have a non-null ``promote`` (only one layout reorder per slate).
    4. One hides a section that the other highlights / compacts / promotes.
    """
    if arm_a.pk == arm_b.pk:
        return True

    cfg_a = arm_a.page_config or {}
    cfg_b = arm_b.page_config or {}

    # Rule 2: overlapping variants keys
    vars_a = set(cfg_a.get("variants", {}).keys())
    vars_b = set(cfg_b.get("variants", {}).keys())
    if vars_a & vars_b:
        return True

    # Rule 3: only one promote per slate
    promote_a = cfg_a.get("promote")
    promote_b = cfg_b.get("promote")
    if promote_a and promote_b:
        return True

    # Rule 4: hide conflicts with compact / variant / promote on the same section
    hide_a = set(cfg_a.get("hide", []))
    hide_b = set(cfg_b.get("hide", []))

    active_a = set(cfg_a.get("compact", [])) | vars_a
    if promote_a:
        active_a.add(promote_a)

    active_b = set(cfg_b.get("compact", [])) | vars_b
    if promote_b:
        active_b.add(promote_b)

    if hide_a & active_b or hide_b & active_a:
        return True

    return False


def _conflicts_with_slate(arm, slate):
    """Return True if *arm* conflicts with any arm already in *slate*."""
    return any(_has_conflict(arm, chosen) for chosen in slate)


# ---------------------------------------------------------------------------
# 5) Merge page_configs for a slate of arms
# ---------------------------------------------------------------------------

def merge_page_configs(arms):
    """
    Merge page_config dicts from multiple arms into one deterministic config.

    compact  → union of all compact section lists (sorted)
    hide     → union of all hidden section lists (sorted)
    promote  → first non-null promote value
    variants → merged dict (conflicts already prevented by choose_slate)
    """
    merged = {
        "compact": set(),
        "hide": set(),
        "promote": None,
        "variants": {},
    }

    for arm in arms:
        cfg = arm.page_config or {}
        merged["compact"] |= set(cfg.get("compact", []))
        merged["hide"] |= set(cfg.get("hide", []))
        if cfg.get("promote") and not merged["promote"]:
            merged["promote"] = cfg["promote"]
        merged["variants"].update(cfg.get("variants", {}))

    # Convert sets to sorted lists for deterministic JSON output
    merged["compact"] = sorted(merged["compact"])
    merged["hide"] = sorted(merged["hide"])

    return merged


# ---------------------------------------------------------------------------
# 6) choose_slate — combinational contextual multi-armed bandit
# ---------------------------------------------------------------------------

SLATE_K = 3   # number of arms per slate


def choose_slate(feature_vector, k=SLATE_K, epsilon=EPSILON):
    """
    Choose a slate of K non-conflicting arms using ε-greedy exploration.

    Algorithm
    ---------
    1. Score every active arm via the linear model (w · x).
       Under-pulled arms (n < MIN_PULLS_PER_ARM) get +inf for warmup.
    2. Greedily pick top-K non-conflicting arms (``no_change`` excluded).
    3. With probability ε, replace ONE random slot with a random valid arm.
    4. If fewer than K valid arms exist, return a shorter slate.

    Returns
    -------
    chosen : list[BanditArm]
    explored : bool
    predicted_scores : dict[str, float]   arm_id → predicted reward
    """
    arms = list(BanditArm.objects.filter(is_active=True))
    if not arms:
        raise ValueError("No active BanditArm rows — run seed_bandit_arms first.")

    # Ensure every arm has LinUCB parameters
    params = {}
    for arm in arms:
        param, _ = LinUCBParam.objects.get_or_create(
            arm=arm,
            defaults={
                "A_matrix": make_initial_A(),
                "b_vector": make_initial_b(),
            },
        )
        params[arm.pk] = param

    # Score arms — under-pulled get +inf (forced warmup)
    arm_scores = []
    for arm in arms:
        if arm.arm_id == "no_change":
            continue  # exclude control from slate
        p = params[arm.pk]
        score = (
            float("inf")
            if p.n < MIN_PULLS_PER_ARM
            else _predict(p.A_matrix, p.b_vector, feature_vector)
        )
        arm_scores.append((arm, score))

    # Sort descending by predicted score
    arm_scores.sort(key=lambda pair: pair[1], reverse=True)

    # --- greedy selection of top-K non-conflicting arms --------------------
    chosen = []
    for arm, _score in arm_scores:
        if len(chosen) >= k:
            break
        if not _conflicts_with_slate(arm, chosen):
            chosen.append(arm)

    # --- ε-greedy exploration: swap one slot with a random valid arm -------
    explored = False
    if chosen and random.random() < epsilon:
        explored = True
        slot = random.randint(0, len(chosen) - 1)
        rest = chosen[:slot] + chosen[slot + 1:]
        candidates = [
            a for a in arms
            if a.arm_id != "no_change"
            and a not in rest
            and not _conflicts_with_slate(a, rest)
        ]
        if candidates:
            replacement = random.choice(candidates)
            chosen = rest[:slot] + [replacement] + rest[slot:]

    # --- predicted scores for logging / debugging --------------------------
    predicted_scores = {}
    for arm in chosen:
        p = params[arm.pk]
        if p.n >= MIN_PULLS_PER_ARM:
            predicted_scores[arm.arm_id] = _predict(
                p.A_matrix, p.b_vector, feature_vector,
            )

    logger.info(
        "Bandit slate: arms=%s explore=%s",
        [a.arm_id for a in chosen],
        explored,
    )

    return chosen, explored, predicted_scores
