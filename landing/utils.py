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
# Intent-score computation  (v1 — simple weighted dwell + click formula)
# ---------------------------------------------------------------------------

def _dwell_score(dwell_ms: int) -> float:
    """Normalise dwell time to 0..1, capping at 30 s so outliers don't dominate."""
    return min(dwell_ms / 1000.0, 30.0) / 30.0


def _click_score(clicks: int) -> float:
    """Normalise click count to 0..1, capping at 5."""
    return min(clicks, 5) / 5.0


def compute_session_intent_scores(session: Session) -> dict:
    """Aggregate Event rows for *session* into intent-feature scores.

    Returns a dict with keys that map directly to Session model fields::

        {
            "price_intent_score":   float,   # 0..1
            "service_intent_score": float,   # 0..1
            "trust_intent_score":   float,   # 0..1
            "quick_scan_score":     float,   # 0 or 1
            "primary_intent":       str,     # "price" / "service" / "trust" / "unknown"
            "max_scroll_pct":       int,     # 0..100
            "engaged_time_ms":      int,     # total active ms
            "cta_clicked":          bool,
        }
    """
    events = Event.objects.filter(session=session)

    # ------------------------------------------------------------------
    # 1. Per-section click counts
    # ------------------------------------------------------------------
    click_qs = events.filter(event_type="click")

    pricing_clicks = click_qs.filter(section="pricing").count()
    services_clicks = click_qs.filter(section="services").count()
    # Trust = testimonials + faq combined
    trust_clicks = click_qs.filter(section__in=["testimonials", "faq"]).count()

    # ------------------------------------------------------------------
    # 2. Per-section dwell totals (from section_dwell events)
    # ------------------------------------------------------------------
    dwell_qs = events.filter(event_type="section_dwell")

    pricing_dwell_ms = (
        dwell_qs.filter(section="pricing")
        .aggregate(total=Sum("duration_ms"))["total"]
        or 0
    )
    services_dwell_ms = (
        dwell_qs.filter(section="services")
        .aggregate(total=Sum("duration_ms"))["total"]
        or 0
    )
    trust_dwell_ms = (
        dwell_qs.filter(section__in=["testimonials", "faq"])
        .aggregate(total=Sum("duration_ms"))["total"]
        or 0
    )

    # ------------------------------------------------------------------
    # 3. Scroll depth  (max depth from scroll_depth events)
    # ------------------------------------------------------------------
    scroll_events = events.filter(event_type="scroll_depth")
    # depth lives either in metadata->depth or directly as a column;
    # the frontend stores it in the top-level payload which ends up in
    # metadata after the "leftover keys" logic in track_interactions.
    max_scroll_pct = 0
    for evt in scroll_events:
        depth = evt.metadata.get("depth", 0) if evt.metadata else 0
        if isinstance(depth, (int, float)) and depth > max_scroll_pct:
            max_scroll_pct = int(depth)

    # ------------------------------------------------------------------
    # 4. Engaged time  (from time_on_page events — take the max)
    # ------------------------------------------------------------------
    top_events = events.filter(event_type="time_on_page")
    engaged_time_ms = 0
    for evt in top_events:
        # duration_ms column is preferred; fall back to metadata.seconds
        ms = evt.duration_ms or 0
        if not ms and evt.metadata:
            secs = evt.metadata.get("seconds", 0)
            ms = int(secs * 1000) if secs else 0
        if ms > engaged_time_ms:
            engaged_time_ms = ms

    # ------------------------------------------------------------------
    # 5. CTA clicked?
    # ------------------------------------------------------------------
    cta_clicked = events.filter(
        Q(is_cta=True) | Q(element__icontains="cta")
    ).exists()

    # ------------------------------------------------------------------
    # 6. Intent scores  (weighted: 60 % dwell + 40 % clicks)
    # ------------------------------------------------------------------
    price_intent = 0.6 * _dwell_score(pricing_dwell_ms) + 0.4 * _click_score(pricing_clicks)
    service_intent = 0.6 * _dwell_score(services_dwell_ms) + 0.4 * _click_score(services_clicks)
    trust_intent = 0.6 * _dwell_score(trust_dwell_ms) + 0.4 * _click_score(trust_clicks)

    # ------------------------------------------------------------------
    # 7. Primary intent  (argmax, with a 0.2 minimum threshold)
    # ------------------------------------------------------------------
    intents = {
        "price": price_intent,
        "service": service_intent,
        "trust": trust_intent,
    }
    best_label = max(intents, key=intents.get)
    primary_intent = best_label if intents[best_label] >= 0.2 else "unknown"

    # ------------------------------------------------------------------
    # 8. Quick-scan score
    #    High scroll (>= 75 %) but low total section dwell (< 5 s)
    #    suggests skimming behaviour rather than deep reading.
    # ------------------------------------------------------------------
    total_dwell_ms = pricing_dwell_ms + services_dwell_ms + trust_dwell_ms
    quick_scan = 1.0 if (max_scroll_pct >= 75 and total_dwell_ms < 5000) else 0.0

    return {
        "price_intent_score": round(price_intent, 4),
        "service_intent_score": round(service_intent, 4),
        "trust_intent_score": round(trust_intent, 4),
        "quick_scan_score": quick_scan,
        "primary_intent": primary_intent,
        "max_scroll_pct": max_scroll_pct,
        "engaged_time_ms": engaged_time_ms,
        "cta_clicked": cta_clicked,
    }
