"""
Scoring utilities for the personalisation layer.

These helpers aggregate tracked events into per-section scores that can
be consumed by the bandit / AI recommendation pipeline.
"""

from collections import Counter

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
