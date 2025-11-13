import uuid
from django.shortcuts import render
from .models import Visitor, Session
from django.utils import timezone
import json
from django.http import JsonResponse
from .models import Session, Interaction
from django.views.decorators.csrf import csrf_exempt

def landing_page(request):
    cookie_id = request.COOKIES.get('visitor_id')

    if cookie_id:
        visitor, _ = Visitor.objects.get_or_create(cookie_id=cookie_id)
    else:
        visitor = Visitor.objects.create()
        cookie_id = str(visitor.cookie_id)

    # Close any active sessions older than X minutes (e.g., 30 min)
    Session.objects.filter(visitor=visitor, is_active=True).update(is_active=False, ended_at=timezone.now())

    # Create a new session for this visit
    session = Session.objects.create(
        visitor=visitor,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        referrer=request.META.get('HTTP_REFERER', '')
    )

    response = render(request, 'landing/index.html', {'session_id': str(session.session_id)})
    response.set_cookie('visitor_id', cookie_id, max_age=60*60*24*365)  # 1 year
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
