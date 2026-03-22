"""
Scoring utilities for the personalisation layer.

These helpers aggregate tracked events into per-section scores that can
be consumed by the bandit / AI recommendation pipeline.
"""

from collections import Counter

from django.db.models import Q, Max, Sum, Count

from .models import Event, Session


def get_user_section_scores(visitor):
    """Calculate per-section engagement scores from a visitor's click history.

    Aggregates *click* events across every session the visitor has had.
    Returns a mapping ``{section_key: normalised_score}`` where scores
    are in the range 0–1.
    """
    sessions = visitor.sessions.order_by("-started_at")
    if not sessions.exists():
        return {}

    # Use the dedicated 'section' column (falls back to 'element' for
    # events that don't carry a section value).
    clicks = (
        Event.objects.filter(session__in=sessions, event_type="click")
        .values_list("section", "element")
    )

    labels = [section or element for section, element in clicks if section or element]
    counter = Counter(labels)
    total = sum(counter.values()) or 1

    # Normalise 0–1
    return {key: count / total for key, count in counter.items()}

def combine_scores(global_scores, user_scores, w_global=0.7, w_user=0.3):
    combined = {}

    all_sections = set(global_scores) | set(user_scores)

    for section in all_sections:
        g = global_scores.get(section, 0)
        u = user_scores.get(section, 0)
        combined[section] = w_global * g + w_user * u

    return combined


# ---------------------------------------------------------------------------
# Intent-score computation  (v2)
#
# Each intent bucket (price / service / trust) is scored from five signals
# collected per-section:
#   1. clicks        – number of click events in the section
#   2. hover_ms      – total hover duration (ms) on interactive elements
#   3. dwell_ms      – total section_dwell time (ms) while section was visible
#   4. cta_clicks    – clicks on CTA elements within the section
#   5. cta_hover_ms  – hover duration on CTA elements within the section
#
# Each signal is normalised to 0..1 using the saturation function
#     f(x) = x / (x + k)
# which maps 0 → 0, increases monotonically, and approaches 1 for large
# values — no hard caps.  The half-saturation constant k (the value of x
# at which f = 0.5) is set to a sensible default for each signal type.
# CTA clicks use min(n, 1) (binary: did they click a CTA at all?).
#
# The five normalised signals are averaged with EQUAL WEIGHTS to produce
# the intent score.  No manual weight tuning — once real data is available
# the weights can be learned or adjusted.
# ---------------------------------------------------------------------------

# Half-saturation constants (k):  f(k) = 0.5.
# These are intentionally round numbers; tune later with real data.
_K_CLICKS   = 3      # 3 clicks  → 0.50
_K_HOVER    = 5000   # 5 s hover → 0.50
_K_DWELL    = 15000  # 15 s dwell → 0.50
_K_CTA_HOVER = 3000  # 3 s CTA hover → 0.50


def _saturate(x: float, k: float) -> float:
    """Saturation normalisation: x / (x + k).  Returns 0..1, no hard cap."""
    if x <= 0:
        return 0.0
    return x / (x + k)


# Which sections map to which intent bucket.
#
# price    → pricing section (plan comparison, price-focused engagement)
# service  → services section (understanding what’s offered)
# trust    → testimonials + faq + trust-bar + about  (all “can I trust
#            this company?” content — reviews, credentials, company story)
# location → locations section (checking physical accessibility → serious
#            purchase consideration)
# contact  → contact section (form engagement, clicking contact details →
#            direct outreach intent)
#
# hero is intentionally excluded — every visitor sees it first so dwell is
# noise, and its CTAs point to #pricing which is tracked there.  header and
# footer carry no meaningful intent signal.
_INTENT_SECTIONS = {
    "price":    ["pricing"],
    "service":  ["services"],
    "trust":    ["testimonials", "faq", "trust-bar", "about"],
    "location": ["locations"],
    "contact":  ["contact"],
}


def _score_intent_group(events, sections: list[str]) -> float:
    """Compute a single intent score (0..1) for *sections* from *events*.

    Collects five signals, normalises each to 0..1, and returns their
    unweighted average.
    """
    section_filter = Q(section__in=sections)
    cta_filter = Q(is_cta=True) | Q(element__icontains="cta")

    # 1. Clicks in section
    clicks = events.filter(event_type="click").filter(section_filter).count()

    # 2. Total hover time (ms) on interactive elements in section
    hover_ms = (
        events.filter(event_type="hover").filter(section_filter)
        .aggregate(total=Sum("duration_ms"))["total"]
        or 0
    )

    # 3. Section dwell time (ms) — how long the section was in viewport
    dwell_ms = (
        events.filter(event_type="section_dwell").filter(section_filter)
        .aggregate(total=Sum("duration_ms"))["total"]
        or 0
    )

    # 4. CTA clicks within the section (binary — any CTA click counts)
    cta_clicks = (
        events.filter(event_type="click")
        .filter(section_filter)
        .filter(cta_filter)
        .count()
    )

    # 5. CTA hover time (ms) within the section
    cta_hover_ms = (
        events.filter(event_type="hover")
        .filter(section_filter)
        .filter(cta_filter)
        .aggregate(total=Sum("duration_ms"))["total"]
        or 0
    )

    # Normalise each signal to 0..1
    click_signal     = _saturate(clicks, _K_CLICKS)
    hover_signal     = _saturate(hover_ms, _K_HOVER)
    dwell_signal     = _saturate(dwell_ms, _K_DWELL)
    cta_click_signal = min(cta_clicks, 1)                 # binary 0 or 1
    cta_hover_signal = _saturate(cta_hover_ms, _K_CTA_HOVER)

    # Equal-weight average of the five signals
    return (click_signal + hover_signal + dwell_signal
            + cta_click_signal + cta_hover_signal) / 5.0


def compute_session_intent_scores(session: Session) -> dict:
    """Aggregate Event rows for *session* into intent-feature scores.

    Returns a dict whose keys map directly to Session model fields::

        {
            "price_intent_score":    float,   # 0..1
            "service_intent_score":  float,   # 0..1
            "trust_intent_score":    float,   # 0..1
            "location_intent_score": float,   # 0..1
            "contact_intent_score":  float,   # 0..1
            "quick_scan_score":      float,   # 0 or 1
            "primary_intent":        str,     # price/service/trust/location/contact/unknown
            "max_scroll_pct":        int,     # 0..100  (raw value from events)
            "engaged_time_ms":       int,     # total active ms (raw value)
            "cta_clicked":           bool,
        }
    """
    events = Event.objects.filter(session=session)

    # ------------------------------------------------------------------
    # 1. Intent scores per bucket (price / service / trust)
    # ------------------------------------------------------------------
    intent_scores = {
        name: _score_intent_group(events, sections)
        for name, sections in _INTENT_SECTIONS.items()
    }

    # ------------------------------------------------------------------
    # 2. Primary intent  (argmax, with a 0.1 minimum threshold)
    # ------------------------------------------------------------------
    best_label = max(intent_scores, key=intent_scores.get)
    primary_intent = best_label if intent_scores[best_label] >= 0.1 else "unknown"

    # ------------------------------------------------------------------
    # 3. Max scroll depth  (simple max from scroll_depth events)
    #    depth is stored in metadata by track_interactions.
    # ------------------------------------------------------------------
    max_scroll_pct = 0
    for evt in events.filter(event_type="scroll_depth"):
        depth = evt.metadata.get("depth", 0) if evt.metadata else 0
        if isinstance(depth, (int, float)) and depth > max_scroll_pct:
            max_scroll_pct = int(depth)

    # ------------------------------------------------------------------
    # 4. Engaged time  (max of time_on_page events, raw ms)
    # ------------------------------------------------------------------
    engaged_time_ms = 0
    for evt in events.filter(event_type="time_on_page"):
        ms = evt.duration_ms or 0
        if not ms and evt.metadata:
            secs = evt.metadata.get("seconds", 0)
            ms = int(secs * 1000) if secs else 0
        if ms > engaged_time_ms:
            engaged_time_ms = ms

    # ------------------------------------------------------------------
    # 5. CTA signals
    #    cta_clicked         – any CTA click anywhere on the page
    #    pricing_cta_clicked – CTA click specifically inside the pricing
    #                          section (plan-select buttons → full conversion)
    # ------------------------------------------------------------------
    cta_clicked = events.filter(
        Q(is_cta=True) | Q(element__icontains="cta")
    ).exists()

    pricing_cta_clicked = events.filter(
        event_type="click",
        section="pricing",
    ).filter(
        Q(is_cta=True) | Q(element__icontains="cta")
    ).exists()

    # ------------------------------------------------------------------
    # 6. Quick-scan score
    #    High scroll (>= 75 %) but low total section dwell (< 5 s)
    #    → user skimmed rather than read.
    # ------------------------------------------------------------------
    total_dwell_ms = (
        events.filter(event_type="section_dwell")
        .aggregate(total=Sum("duration_ms"))["total"]
        or 0
    )
    quick_scan = 1.0 if (max_scroll_pct >= 75 and total_dwell_ms < 5000) else 0.0

    return {
        "price_intent_score":    round(intent_scores["price"], 4),
        "service_intent_score":  round(intent_scores["service"], 4),
        "trust_intent_score":    round(intent_scores["trust"], 4),
        "location_intent_score": round(intent_scores["location"], 4),
        "contact_intent_score":  round(intent_scores["contact"], 4),
        "quick_scan_score":      quick_scan,
        "primary_intent":        primary_intent,
        "max_scroll_pct":        max_scroll_pct,
        "engaged_time_ms":       engaged_time_ms,
        "cta_clicked":           cta_clicked,
        "pricing_cta_clicked":   pricing_cta_clicked,
    }
