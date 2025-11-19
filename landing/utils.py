from collections import Counter
from .models import Interaction, Session

def get_user_section_scores(visitor):
    """Calculate section scores by aggregating clicks across all sessions.

    This matches the behavior in `generate_demo_recommendations` which
    considers all sessions when computing click counts for layout choices.
    Returns a mapping section -> normalized score (0..1).
    """
    sessions = visitor.sessions.order_by('-started_at')
    if not sessions.exists():
        return {}

    interactions = Interaction.objects.filter(session__in=sessions, event_type="click")
    clicks = [i.element for i in interactions if i.element]

    counter = Counter(clicks)
    total = sum(counter.values()) or 1

    # Normalize 0–1
    return {section: count / total for section, count in counter.items()}

def combine_scores(global_scores, user_scores, w_global=0.7, w_user=0.3):
    combined = {}

    all_sections = set(global_scores) | set(user_scores)

    for section in all_sections:
        g = global_scores.get(section, 0)
        u = user_scores.get(section, 0)
        combined[section] = w_global * g + w_user * u

    return combined
