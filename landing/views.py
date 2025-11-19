from django.shortcuts import render
from django.utils import timezone
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from collections import Counter
import uuid
from .models import Visitor, Session, Interaction
from .bandit import SectionBandit
from .utils import get_user_section_scores, combine_scores

def generate_demo_recommendations(visitor):
    """Generate layout and customizations based on last session's clicks.

    This inspects the most recent session for the visitor, counts clicks per
    section (Interaction.element should contain the section id like 'pricing'),
    sorts sections by click frequency, and returns a layout plus simple
    customizations (header text and optional highlight for the top section).
    """
    sessions = visitor.sessions.order_by('-started_at')
    session_count = sessions.count()

    # Default layout order (expanded to include newer sections)
    default_layout = [
        "header",
        "features",
        "services",
        "pricing",
        "testimonials",
        "cta",
        "contact",
    ]
    layout = default_layout.copy()
    customizations = {
        "header": {"text": "Fast. Clean. Reliable.", "style": "default"},
    }

    # If there are 1 or fewer sessions, keep the default layout (no reordering).
    if session_count <= 1:
        # debug info: which sessions would have been considered (none or one)
        debug = {
            'used_default': True,
            'section_clicks': {},
            'sessions_considered': [str(s.session_id) for s in sessions[:20]],
            'session_count_considered': session_count,
        }
        return {"layout": layout, "customizations": customizations, "debug": debug}

    # For visitors with more than one session, aggregate across all sessions
    target_sessions = sessions

    # Gather clicks per section across the chosen sessions
    interactions = Interaction.objects.filter(session__in=target_sessions, event_type="click")
    section_clicks = Counter(i.element for i in interactions if i.element)

    if section_clicks:
        # Sort layout by sections with highest click count first
        sorted_sections = sorted(default_layout, key=lambda s: -section_clicks.get(s, 0))
        layout = [sec for sec in sorted_sections if sec in default_layout]

        # Optional: highlight the most clicked section
        top_section, _ = section_clicks.most_common(1)[0]
        if top_section in default_layout and top_section != 'header':
            customizations[top_section] = {"highlight": True}

        # Adjust header message if multiple visits
        if visitor.sessions.count() > 1:
            customizations["header"] = {"text": "Welcome back!", "style": "highlight"}

    # Debug info to help surface why layout was chosen
    # list the session ids we considered (limits to 20 ids for readability)
    sessions_considered = [str(s.session_id) for s in (target_sessions[:20] if hasattr(target_sessions, '__iter__') else target_sessions)]
    debug = {
        'used_default': not bool(section_clicks),
        'section_clicks': dict(section_clicks),
        'sessions_considered': sessions_considered,
        'session_count_considered': session_count,
    }

    return {"layout": layout, "customizations": customizations, "debug": debug}

def generate_recommendations(visitor):
    # 1. Load valid sections (arms)
    config = json.load(open("landing/bandit_config.json"))
    default_layout = config["arms"]

    # 2. Global scores from bandit
    bandit = SectionBandit()
    global_scores = bandit.get_global_scores()

    # 3. Personal scores
    user_scores = get_user_section_scores(visitor)

    # 4. Combine them (expose weights in debug)
    w_global = 0.7
    w_user = 0.3
    scores = combine_scores(global_scores, user_scores, w_global=w_global, w_user=w_user)

    # 5. Order sections by score
    ordered_sections = sorted(default_layout, key=lambda s: -scores.get(s, 0))

    # 6. Build customizations (simple for now)
    customizations = {
        "header": {
            "text": "Welcome back!" if visitor.sessions.count() > 1 else
                    "Fast. Clean. Reliable.",
            "style": "highlight" if visitor.sessions.count() > 1 else "default",
        }
    }

    # Debug info: clicks & sessions considered (limit to 20 ids for readability)
    sessions = visitor.sessions.order_by('-started_at')
    session_count = sessions.count()
    interactions = Interaction.objects.filter(session__in=sessions, event_type="click")
    section_clicks = Counter(i.element for i in interactions if i.element)

    sessions_considered = [str(s.session_id) for s in (sessions[:20] if hasattr(sessions, '__iter__') else sessions)]
    debug = {
        'used_default': not bool(section_clicks),
        'section_clicks': dict(section_clicks),
        'sessions_considered': sessions_considered,
        'session_count_considered': session_count,
        'weights': {'w_global': w_global, 'w_user': w_user},
        'default_layout': default_layout,
    }

    return {
        "layout": ordered_sections,
        "scores": scores,
        "global_scores": global_scores,
        "user_scores": user_scores,
        "customizations": customizations,
        "debug": debug,
    }

def landing_page(request):
    cookie_id = request.COOKIES.get("visitor_id")

    if cookie_id:
        visitor, _ = Visitor.objects.get_or_create(cookie_id=cookie_id)
    else:
        visitor = Visitor.objects.create()
        cookie_id = str(visitor.cookie_id)

    # Close any old active sessions
    Session.objects.filter(visitor=visitor, is_active=True).update(is_active=False, ended_at=timezone.now())

    # Create a new session
    session = Session.objects.create(
        visitor=visitor,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        referrer=request.META.get("HTTP_REFERER", "")
    )

    # Generate layout recommendations
    recommendations = generate_recommendations(visitor)

    response = render(
        request,
        "landing/index_dynamic.html",
        {
            "session_id": str(session.session_id),
            "recommendations_json": json.dumps(recommendations),
        }
    )

    response.set_cookie("visitor_id", cookie_id, max_age=60 * 60 * 24 * 365)
    return response


@csrf_exempt
def track_interactions(request):
    if request.method == "POST":
        data = json.loads(request.body)
        session_id = data.get("session_id")
        events = data.get("events", [])

        try:
            session = Session.objects.get(session_id=session_id)
        except Session.DoesNotExist:
            return JsonResponse({"error": "Invalid session"}, status=400)

        for e in events:
            Interaction.objects.create(
                session=session,
                event_type=e.get("event_type"),
                element=e.get("element"),
                additional_data=e.get("additional_data", {}),
            )

        return JsonResponse({"status": "success"})
    return JsonResponse({"error": "Invalid method"}, status=405)
