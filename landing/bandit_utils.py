"""
Bandit utility functions — Linear contextual bandit with ε-greedy exploration.

build_context    – turn a visitor into a list of 8 numbers (the feature vector)
choose_arm       – predict which arm will work best, with ε-greedy exploration
update_stats     – learn from the result of a session (adjust weights)

How it works (plain English)
----------------------------
Instead of putting visitors into rigid buckets like "desktop_price",
each visitor is described by a list of 8 numbers — their feature vector.
Nothing is thrown away; all the continuous scores are kept as-is.

Each arm learns a set of **weights** — one weight per feature. To predict
whether an arm will work for a visitor, multiply each feature by its
weight and add them up:

    predicted_reward = sum(feature_i × weight_i  for each feature)

The arm with the highest predicted reward wins (90% of the time).
The other 10% we pick a random arm to keep exploring (ε-greedy).

When the session ends and we know if the visitor clicked a CTA
(reward = 1.0) or not (reward = 0.0), we update the arm's stored
parameters (A_matrix and b_vector in LinUCBParam) so the weights
become more accurate for similar visitors in the future.

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
MIN_PULLS_PER_ARM = 5       # try every arm at least 5 times before trusting predictions
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

    Returns ``(arm, explored_flag)``.
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
        return chosen, True

    # --- ε-greedy ----------------------------------------------------------
    if random.random() < epsilon:
        chosen = random.choice(arms)
        logger.info("Bandit explore (ε=%.2f): arm=%s", epsilon, chosen.arm_id)
        return chosen, True

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
    return best_arm, False


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
