"""
Bandit utility functions (contextual multi-armed bandit).

build_context    – extract context features from visitor + request
bucketize        – turn a context dict into a discrete bucket string
choose_arm       – epsilon-greedy arm selection within a bucket
update_stats     – record a reward observation for (bucket, arm)
"""

import logging
import random

from .models import BanditArm, BanditArmStat, Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EPSILON = 0.10          # exploration probability
MIN_TRIES_PER_ARM = 5   # warmup: force-explore until each arm has this many pulls

# ---------------------------------------------------------------------------
# 1) build_context
# ---------------------------------------------------------------------------

def build_context(visitor, request) -> dict:
    """
    Extract context features for the bandit decision.

    Returns a dict with:
        device_type          – "mobile" or "desktop"
        last_primary_intent  – from the most recent *ended* session
        last_scores          – dict of intent scores from that session
    """
    # --- device type (simple UA heuristic) ---------------------------------
    ua = request.META.get("HTTP_USER_AGENT", "").lower()
    mobile_keywords = ("mobile", "android", "iphone", "ipod", "ipad", "opera mini", "iemobile")
    device_type = "mobile" if any(kw in ua for kw in mobile_keywords) else "desktop"

    # --- last ended session for this visitor --------------------------------
    last_session = (
        Session.objects
        .filter(visitor=visitor, ended_at__isnull=False)
        .order_by("-ended_at")
        .first()
    )

    if last_session:
        last_primary_intent = last_session.primary_intent or "unknown"
        last_scores = {
            "price": last_session.price_intent_score,
            "service": last_session.service_intent_score,
            "trust": last_session.trust_intent_score,
            "location": last_session.location_intent_score,
            "contact": last_session.contact_intent_score,
        }
    else:
        last_primary_intent = "unknown"
        last_scores = {}

    return {
        "device_type": device_type,
        "last_primary_intent": last_primary_intent,
        "last_scores": last_scores,
    }


# ---------------------------------------------------------------------------
# 2) bucketize
# ---------------------------------------------------------------------------

def bucketize(context: dict) -> str:
    """
    Convert a context dict into a discrete bucket string.

    Format: ``{device_type}_{last_primary_intent}``
    Examples: ``mobile_price``, ``desktop_unknown``, ``desktop_trust``
    """
    device = context.get("device_type", "desktop")
    intent = context.get("last_primary_intent", "unknown")
    return f"{device}_{intent}"


# ---------------------------------------------------------------------------
# 3) choose_arm
# ---------------------------------------------------------------------------

def choose_arm(bucket: str, epsilon: float = EPSILON):
    """
    Epsilon-greedy arm selection within *bucket*.

    Warmup: if any active arm has fewer than ``MIN_TRIES_PER_ARM`` pulls
    in this bucket, that arm is chosen (forced exploration).

    Returns ``(arm, explore_flag)``.
    """
    arms = list(BanditArm.objects.filter(is_active=True))
    if not arms:
        raise ValueError("No active BanditArm rows — run seed_bandit_arms first.")

    # Fetch existing stats for this bucket in one query
    stats_qs = BanditArmStat.objects.filter(
        context_bucket=bucket, arm__in=arms,
    ).select_related("arm")
    stats_by_arm = {s.arm_id: s for s in stats_qs}

    # --- warmup phase: force-explore under-tried arms ----------------------
    under_tried = [a for a in arms if stats_by_arm.get(a.pk) is None
                   or stats_by_arm[a.pk].n < MIN_TRIES_PER_ARM]
    if under_tried:
        chosen = random.choice(under_tried)
        logger.info("Bandit warmup: bucket=%s  arm=%s", bucket, chosen.arm_id)
        return chosen, True   # explore

    # --- epsilon-greedy ----------------------------------------------------
    if random.random() < epsilon:
        chosen = random.choice(arms)
        logger.info("Bandit explore: bucket=%s  arm=%s  eps=%.2f", bucket, chosen.arm_id, epsilon)
        return chosen, True   # explore
    else:
        # exploit: pick arm with highest mean_reward in this bucket
        best_arm = max(arms, key=lambda a: stats_by_arm[a.pk].mean_reward)
        logger.info("Bandit exploit: bucket=%s  arm=%s  mean=%.3f",
                     bucket, best_arm.arm_id,
                     stats_by_arm[best_arm.pk].mean_reward)
        return best_arm, False  # exploit


# ---------------------------------------------------------------------------
# 4) update_stats
# ---------------------------------------------------------------------------

def update_stats(bucket: str, arm: BanditArm, reward: float):
    """
    Incrementally update running statistics for (bucket, arm).

    Creates the BanditArmStat row if it doesn't exist yet.
    """
    stat, _created = BanditArmStat.objects.get_or_create(
        context_bucket=bucket,
        arm=arm,
    )
    stat.n += 1
    stat.sum_reward += reward
    stat.mean_reward = stat.sum_reward / stat.n
    stat.save()
    logger.info(
        "Bandit update_stats: bucket=%s arm=%s reward=%.1f → n=%d mean=%.3f",
        bucket, arm.arm_id, reward, stat.n, stat.mean_reward,
    )
