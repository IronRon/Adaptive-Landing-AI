from django.shortcuts import render
from .models import Visitor, Session
from django.utils import timezone
import json
from django.http import JsonResponse
from .models import Session, Interaction
from django.views.decorators.csrf import csrf_exempt
from collections import Counter
import json
import uuid
from django.shortcuts import render
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Visitor, Session, Interaction

def generate_demo_recommendations(visitor):
    """Generate layout and customizations based on last session's clicks.

    This inspects the most recent session for the visitor, counts clicks per
    section (Interaction.element should contain the section id like 'pricing'),
    sorts sections by click frequency, and returns a layout plus simple
    customizations (header text and optional highlight for the top section).
    """
    sessions = visitor.sessions.order_by('-started_at')
    session_count = sessions.count()

    # Default layout order
    default_layout = ["header", "services", "pricing", "cta"]
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
    recommendations = generate_demo_recommendations(visitor)

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
