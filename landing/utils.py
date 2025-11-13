from .models import Interaction
from collections import Counter

def get_recommendations(visitor):
    """
    Simple rule-based logic to emulate AI recommendations.
    Looks at last session's interactions and returns JSON.
    """
    sessions = visitor.sessions.all().order_by('-started_at')
    if not sessions.exists():
        return {"layout": [], "style_changes": {}, "messages": []}

    latest = sessions.first()
    interactions = Interaction.objects.filter(session=latest)

    clicked = [i.element for i in interactions if i.event_type == "click"]
    click_counts = Counter(clicked)

    rec = {"layout": [], "style_changes": {}, "messages": []}

    # Example rule 1: Move pricing higher if user clicked pricing section
    if "H4" in click_counts or "PRICING" in str(clicked).upper():
        rec["layout"].append({"move_section": "pricing", "position": "top"})
        rec["messages"].append("Pricing moved up due to frequent interest.")

    # Example rule 2: Enlarge CTA if clicked
    if "A" in click_counts or "BUTTON" in str(clicked).upper():
        rec["style_changes"]["cta"] = {"scale": 1.3, "highlight": True}
        rec["messages"].append("CTA emphasized for returning visitor.")

    # Example rule 3: Add welcome text if returning user
    rec["messages"].append("Welcome back!")

    return rec
