"""
Bandit utility functions — Linear contextual bandit with ε-greedy exploration.

build_context    – extract a numeric feature vector from visitor + request
choose_arm       – predict reward per arm via linear model, ε-greedy selection
update_stats     – online ridge regression update for (arm, context, reward)

Replaces the old bucket-based approach: instead of discretising context into
buckets like "desktop_price", the bandit now uses a continuous feature vector
and learns a weight vector per arm via online ridge regression.

How it works (plain English)
----------------------------
Each arm has a set of learned **weights** — one per context feature.
When a visitor arrives, we multiply each feature by the arm's weight and
add them up.  That sum is the *predicted reward* for the arm.

    predicted_reward = sum(feature_i × weight_i for each feature)

With probability ε we ignore the prediction and pick a random arm
(explore); otherwise we pick the arm with the highest predicted reward
(exploit).  Same ε-greedy logic as before — just smarter predictions.

When the session ends and a reward (CTA clicked = 1.0, else 0.0) arrives
we adjust the weights so the prediction gets more accurate next time.

Feature vector (d=8)
--------------------
    [is_mobile, price_score, service_score, trust_score,
     location_score, contact_score, visit_number_norm, bias]
"""

import logging
import random

from .models import BanditArm, LinUCBParam, Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EPSILON = 0.10              # exploration probability
MIN_PULLS_PER_ARM = 5       # warmup: uniform exploration until each arm has this many pulls
LAMBDA_REG = 1.0             # ridge regression regularisation (initial A = λI)

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
# Pure-Python linear algebra helpers  (d=8 — no numpy needed)
# ---------------------------------------------------------------------------

def _dot(a, b):
    """Dot product of two vectors."""
    return sum(ai * bi for ai, bi in zip(a, b))


def _outer(a, b):
    """Outer product: returns a d×d matrix (list of lists)."""
    return [[ai * bj for bj in b] for ai in a]


def _mat_add(A, B):
    """Element-wise addition of two d×d matrices."""
    return [[A[i][j] + B[i][j] for j in range(len(A[0]))] for i in range(len(A))]


def _vec_add(a, b):
    """Element-wise addition of two vectors."""
    return [ai + bi for ai, bi in zip(a, b)]


def _vec_scale(v, s):
    """Scalar multiplication of a vector."""
    return [vi * s for vi in v]


def _identity(d, lam=1.0):
    """Return a d×d identity matrix scaled by λ."""
    return [[lam if i == j else 0.0 for j in range(d)] for i in range(d)]


def _zeros(d):
    """Return a zero vector of length d."""
    return [0.0] * d


def _solve(A, b):
    """
    Solve Ax = b via Gauss-Jordan elimination with partial pivoting.

    A is d×d, b is length-d.  Returns x as a list of floats.
    Does NOT modify the inputs (works on copies).
    """
    d = len(b)
    # Build augmented matrix [A | b]
    aug = [A[i][:] + [b[i]] for i in range(d)]

    for col in range(d):
        # Partial pivoting — swap with the row that has the largest abs value
        max_row = max(range(col, d), key=lambda r: abs(aug[r][col]))
        aug[col], aug[max_row] = aug[max_row], aug[col]

        pivot = aug[col][col]
        if abs(pivot) < 1e-12:
            continue  # near-singular — skip this column

        # Scale pivot row so pivot becomes 1
        inv_pivot = 1.0 / pivot
        for j in range(col, d + 1):
            aug[col][j] *= inv_pivot

        # Eliminate this column in all other rows
        for row in range(d):
            if row == col:
                continue
            factor = aug[row][col]
            for j in range(col, d + 1):
                aug[row][j] -= factor * aug[col][j]

    return [aug[i][d] for i in range(d)]


def _predict(A_matrix, b_vector, x):
    """
    Predict reward for context vector x given model parameters (A, b).

    Works out the weight vector:  θ = A⁻¹ · b
    Then returns:  predicted_reward = dot(x, θ)
    """
    theta = _solve(A_matrix, b_vector)
    return _dot(x, theta)


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
                "A_matrix": _identity(FEATURE_DIM, LAMBDA_REG),
                "b_vector": _zeros(FEATURE_DIM),
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
    Online ridge regression update for the given arm.

    A ← A + x·xᵀ       (accumulate information about the context)
    b ← b + reward · x  (accumulate reward signal)

    When we later need the weight vector:  θ = A⁻¹·b
    This is standard online ridge regression — the same maths used by
    LinUCB but without the confidence bonus (we use ε-greedy instead).
    """
    param, _ = LinUCBParam.objects.get_or_create(
        arm=arm,
        defaults={
            "A_matrix": _identity(FEATURE_DIM, LAMBDA_REG),
            "b_vector": _zeros(FEATURE_DIM),
        },
    )

    x = feature_vector
    A = param.A_matrix
    b = param.b_vector

    # A ← A + x·xᵀ
    xxT = _outer(x, x)
    A = _mat_add(A, xxT)

    # b ← b + reward · x
    rx = _vec_scale(x, reward)
    b = _vec_add(b, rx)

    param.A_matrix = A
    param.b_vector = b
    param.n += 1
    param.save()

    logger.info(
        "Bandit update: arm=%s reward=%.1f n=%d",
        arm.arm_id, reward, param.n,
    )
