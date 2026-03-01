"""
Views for the landing app.

Tracking endpoints
------------------
accept_cookies      – POST /accept-cookies/    → create / resume visitor, start session
track_interactions  – POST /track-interactions/ → store batched frontend events
end_session         – POST /end-session/        → mark session ended, compute intent scores

Page-serving views
------------------
demo_landing_page   – static landing page (no DB, no bandit)
landing_page        – dynamic landing page with AI recommendations

Builder views are unchanged and kept at the bottom of the file.
"""

from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from collections import Counter
import uuid

from .models import (
    AIRecommendation,
    LandingPage,
    LandingSection,
    Visitor,
    Session,
    Event,
)
from .utils import get_user_section_scores, combine_scores, compute_session_intent_scores
from .ai_llm import generate_llm_recommendations
from django.core.exceptions import ValidationError

from .models import BanditArm, BanditDecision
from .bandit_utils import build_context, bucketize, choose_arm, update_stats

logger = logging.getLogger(__name__)

def generate_recommendations(visitor, sections, combined_css, page):
    # Use bandit + user data and call the LLM to produce layout/customizations.
    # If LLM fails, fall back to rule-based recommendations.
    # 1. Load valid sections (arms)
    default_layout = [sec.key for sec in sections]
    assets = {
        sec.key: {
            "html": sec.html,
        }
        for sec in sections
    }

    # 2. Global scores (placeholder — old UCB1 bandit removed)
    global_scores = {sec.key: 1.0 for sec in sections}

    # 3. Personal scores
    user_scores = get_user_section_scores(visitor)

    # Build the prompt data
    prompt_data = {
        "default_layout": default_layout,
        "global_scores": global_scores,
        "user_scores": user_scores,
        "visitor_meta": {
            "session_count": visitor.sessions.count(),
            "click_counts": user_scores,
        },
        "assets": assets,
        "combined_css": combined_css,
    }

    # ---- CALL THE AI ----
    ai_output = generate_llm_recommendations(prompt_data)

    # If AI failed or returned empty JSON → fallback to rule-based
    if not ai_output or "layout" not in ai_output:
        return legacy_rule_based_recommendations(default_layout, visitor, global_scores, user_scores)

    # save to DB
    AIRecommendation.objects.create(
        page=page,
        visitor=visitor,
        response_json=ai_output
    )

    # Merge AI output with debug info
    ai_output["debug"] = {
        "global_scores": global_scores,
        "user_scores": user_scores,
        "used_llm": True,
    }

    return ai_output

def legacy_rule_based_recommendations(default_layout, visitor, global_scores, user_scores):
    # Simple fallback: sort sections by combined score and provide basic header customizations
    ordered = sorted(default_layout, key=lambda s: -(global_scores.get(s, 0) + user_scores.get(s, 0)))

    custom = {
        "header": {
            "text": "Welcome back!" if visitor.sessions.count() > 1 else "Fast. Clean. Reliable.",
            "style": "highlight" if visitor.sessions.count() > 1 else "default",
        }
    }

    return {
        "layout": ordered,
        "customizations": custom,
        "debug": {
            "fallback": True,
        },
    }

def build_combined_css(page):
    # Merge global page CSS and per-section CSS into a single string
    css_parts = [page.global_css]

    for sec in page.sections.order_by("order"):
        if sec.css.strip():
            css_parts.append(sec.css)

    return "\n\n".join(css_parts)


def demo_landing_page(request):
    """Hard-coded demo landing page — no DB, no bandit, just the frontend."""
    return render(request, 'landing/landing_page.html', {
        # Pass variant classes here to test different states, e.g.:
        # 'hero_variant': 'hero-cta-emphasis',
        # 'pricing_variant': 'highlight-plan-2',
        # 'testimonials_variant': 'testimonials-single',
        # 'faq_variant': 'faq-compact-top3',
        # 'services_variant': 'featured-service-1',
    })


def landing_page(request):
    # Main landing view:
    # - If no visitor cookie: show cookie popup and do not track
    # - If cookie exists: create session, close old sessions, run recommendations and render page
    cookie_id = request.COOKIES.get("visitor_id")

    page = LandingPage.objects.first()
    if not page:
        return render(request, "landing/index_static.html", {})
    sections = page.sections.order_by("order")

    section_data = {
        sec.key: {
            "html": sec.html,
            "css": sec.css
        }
        for sec in sections
    }

    combined_css = build_combined_css(page)

    if not cookie_id:
        # No cookies yet → First visit → NO tracking
        return render(request, "landing/index_dynamic.html", {
            "session_id": None,
            "builder_sections": json.dumps(section_data),
            "combined_css": combined_css,
            "recommendations_json": json.dumps({}), 
            "show_cookie_popup": True,
        })

    
    visitor= Visitor.objects.get(cookie_id=cookie_id)

    # Close any old active sessions
    Session.objects.filter(visitor=visitor, is_active=True).update(is_active=False, ended_at=timezone.now())

    # Create a new session
    session = Session.objects.create(
        visitor=visitor,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        referrer=request.META.get("HTTP_REFERER", "")
    )

    # Only call the AI recommendations when an existing cookie was present
    recommendations = generate_recommendations(visitor, sections, combined_css, page)

    response = render(
        request,
        "landing/index_dynamic.html",
        {
            "session_id": str(session.session_id),
            "builder_sections": json.dumps(section_data),
            "combined_css": combined_css,
            "recommendations_json": json.dumps(recommendations),
        }
    )

    return response


@csrf_exempt
def track_interactions(request):
    """
    POST /track-interactions/

    Receive batched interaction events from the frontend tracker and persist
    them to the database.

    Expected JSON payload::

        {
            "session_id": "<uuid>",
            "events": [
                {
                    "type": "click",
                    "ts": "2026-02-27T12:00:00.000Z",
                    "url": "/",
                    "section": "hero",
                    "element": "hero-cta",
                    "is_cta": true,
                    "tag": "button",
                    "text": "Get Started"
                },
                ...
            ]
        }

    Known fields are stored as real columns; everything else goes into
    ``Event.metadata`` so the frontend can evolve without backend changes.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST is allowed."}, status=405)

    # --- parse body --------------------------------------------------------
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    # --- resolve session ---------------------------------------------------
    session_id = data.get("session_id")
    if not session_id:
        return JsonResponse({"error": "Missing session_id."}, status=400)

    try:
        session = Session.objects.get(session_id=session_id)
    except (Session.DoesNotExist, ValidationError, ValueError):
        return JsonResponse({"error": "Unknown or invalid session_id."}, status=404)

    # --- process events ----------------------------------------------------
    raw_events = data.get("events", [])
    if not raw_events:
        return JsonResponse({"status": "ok", "stored": 0})

    # Fields that map to dedicated Event columns — everything else → metadata
    COLUMN_FIELDS = {"type", "ts", "url", "section", "element", "is_cta", "duration_ms"}

    events_to_create = []
    for evt in raw_events:
        # Collect leftover keys into metadata
        metadata = {k: v for k, v in evt.items() if k not in COLUMN_FIELDS}

        # Parse the client-side ISO timestamp; fall back to server time
        ts_raw = evt.get("ts")
        try:
            timestamp = parse_datetime(ts_raw) if ts_raw else timezone.now()
            if timestamp is None:
                timestamp = timezone.now()
        except (ValueError, TypeError):
            timestamp = timezone.now()

        events_to_create.append(
            Event(
                session=session,
                event_type=evt.get("type", "unknown"),
                timestamp=timestamp,
                url=evt.get("url", ""),
                section=evt.get("section") or "",
                element=evt.get("element") or "",
                is_cta=evt.get("is_cta"),
                duration_ms=evt.get("duration_ms"),
                metadata=metadata,
            )
        )

    Event.objects.bulk_create(events_to_create)
    logger.debug("Stored %d events for session %s", len(events_to_create), session_id)

    return JsonResponse({"status": "ok", "stored": len(events_to_create)})


# ---------------------------------------------------------------------------
# Session end & intent-score computation
# ---------------------------------------------------------------------------

@csrf_exempt
def end_session(request):
    """
    POST /end-session/

    Called by the frontend (via sendBeacon) when the user leaves the page.
    Marks the session as ended and computes intent-feature scores from the
    Event rows recorded during the session.

    Payload::

        { "session_id": "<uuid>" }

    Idempotent — safe to call more than once for the same session.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST is allowed."}, status=405)

    # --- consent gate ------------------------------------------------------
    consent = request.COOKIES.get("sw_cookie_consent")
    if not consent:
        # Also accept visitor_id cookie as implicit proof of consent
        if not request.COOKIES.get("visitor_id"):
            return JsonResponse({"error": "Cookie consent not given."}, status=403)

    # --- parse body --------------------------------------------------------
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    session_id = data.get("session_id")
    if not session_id:
        return JsonResponse({"error": "Missing session_id."}, status=400)

    # --- resolve session ---------------------------------------------------
    try:
        session = Session.objects.select_related("visitor").get(session_id=session_id)
    except (Session.DoesNotExist, ValidationError, ValueError):
        return JsonResponse({"error": "Unknown or invalid session_id."}, status=404)

    # --- ownership check (prevent poisoning) --------------------------------
    visitor_cookie = request.COOKIES.get("visitor_id")
    if not visitor_cookie or str(session.visitor.cookie_id) != visitor_cookie:
        return JsonResponse({"error": "Session does not belong to this visitor."}, status=403)

    # --- mark ended --------------------------------------------------------
    if not session.ended_at:
        session.ended_at = timezone.now()
    session.is_active = False

    # --- compute intent scores from events ---------------------------------
    scores = compute_session_intent_scores(session)

    session.max_scroll_pct = scores["max_scroll_pct"]
    session.engaged_time_ms = scores["engaged_time_ms"]
    session.cta_clicked = scores["cta_clicked"]
    session.price_intent_score = scores["price_intent_score"]
    session.service_intent_score = scores["service_intent_score"]
    session.trust_intent_score = scores["trust_intent_score"]
    session.location_intent_score = scores["location_intent_score"]
    session.contact_intent_score = scores["contact_intent_score"]
    session.quick_scan_score = scores["quick_scan_score"]
    session.primary_intent = scores["primary_intent"]

    session.save()

    # --- bandit reward update (only for visit_number >= 2) -----------------
    if session.visit_number >= 2:
        try:
            decision = BanditDecision.objects.select_related("arm").get(session=session)
            reward = 1.0 if session.cta_clicked else 0.0
            decision.reward = reward
            decision.save(update_fields=["reward"])
            update_stats(decision.context_bucket, decision.arm, reward)
            logger.info(
                "Bandit reward: session=%s arm=%s reward=%.1f",
                session.session_id, decision.arm.arm_id, reward,
            )
        except BanditDecision.DoesNotExist:
            logger.debug("No BanditDecision for session %s — skipping reward.", session.session_id)
        except Exception:
            logger.exception("Bandit reward update failed for session %s.", session.session_id)

    logger.info(
        "end_session: session=%s  primary_intent=%s  "
        "price=%.2f  service=%.2f  trust=%.2f  location=%.2f  contact=%.2f",
        session.session_id,
        scores["primary_intent"],
        scores["price_intent_score"],
        scores["service_intent_score"],
        scores["trust_intent_score"],
        scores["location_intent_score"],
        scores["contact_intent_score"],
    )

    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Cookie acceptance & session creation
# ---------------------------------------------------------------------------

@csrf_exempt
def accept_cookies(request):
    """
    POST /accept-cookies/

    Called by the frontend in two situations:

    1. **First visit** — user clicks "Accept Cookies".
       Creates a new :model:`landing.Visitor` and :model:`landing.Session`,
       sets the ``visitor_id`` cookie (1-year expiry).

    2. **Return visit** — consent cookie already exists, page just loaded.
       Finds the existing Visitor (from ``visitor_id`` cookie), closes any
       stale active sessions, and creates a fresh Session for this page-load.

    Returns JSON::

        {
            "status":     "accepted",
            "session_id": "<uuid>",
            "visitor_id": "<uuid>",
            "is_new":     true | false
        }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST is allowed."}, status=405)

    cookie_id = request.COOKIES.get("visitor_id")
    is_new = False

    # --- resolve or create visitor -----------------------------------------
    if cookie_id:
        try:
            visitor = Visitor.objects.get(cookie_id=cookie_id)
            visitor.save()  # triggers auto_now → updates last_seen
        except (Visitor.DoesNotExist, ValueError):
            # Cookie held a stale / invalid UUID → treat as new visitor
            visitor = Visitor.objects.create()
            is_new = True
    else:
        visitor = Visitor.objects.create()
        is_new = True

    # --- close stale active sessions ---------------------------------------
    Session.objects.filter(
        visitor=visitor, is_active=True,
    ).update(is_active=False, ended_at=timezone.now())

    # --- compute visit_number ----------------------------------------------
    visit_number = Session.objects.filter(visitor=visitor).count() + 1

    # --- create a fresh session for this page-load -------------------------
    session = Session.objects.create(
        visitor=visitor,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        referrer=request.META.get("HTTP_REFERER", ""),
        visit_number=visit_number,
    )

    logger.info(
        "accept_cookies: visitor=%s  session=%s  is_new=%s  visit_number=%d",
        visitor.cookie_id, session.session_id, is_new, visit_number,
    )

    # --- contextual bandit -------------------------------------------------
    page_config = {}   # default: no layout changes (control)
    arm_id = None

    if visit_number >= 2:
        try:
            context = build_context(visitor, request)
            bucket = bucketize(context)
            arm, explored = choose_arm(bucket)

            from .bandit_utils import EPSILON as _eps
            BanditDecision.objects.create(
                session=session,
                visitor=visitor,
                context_bucket=bucket,
                context_json=context,
                arm=arm,
                explore=explored,
                epsilon=_eps,
            )

            page_config = arm.page_config or {}
            arm_id = arm.arm_id
            logger.info(
                "Bandit chose arm=%s for bucket=%s (explore=%s)",
                arm.arm_id, bucket, explored,
            )
        except Exception:
            logger.exception("Bandit decision failed — falling back to control.")

    # --- build response with cookie ----------------------------------------
    response = JsonResponse({
        "status": "accepted",
        "session_id": str(session.session_id),
        "visitor_id": str(visitor.cookie_id),
        "is_new": is_new,
        "visit_number": visit_number,
        "arm_id": arm_id,
        "page_config": page_config,
    })

    # Persist visitor_id cookie for 1 year
    response.set_cookie(
        "visitor_id",
        str(visitor.cookie_id),
        max_age=60 * 60 * 24 * 365,   # 1 year
        httponly=False,                 # JS needs to read it
        samesite="Lax",
        path="/",
    )

    return response


def builder_index(request):
    # Builder UI: list landing pages
    pages = LandingPage.objects.all()
    return render(request, "builder/index.html", {"pages": pages})

def builder_new_page(request):
    # Builder: create a new landing page (POST) or show form (GET)
    if request.method == "POST":
        name = request.POST.get("name", "My Landing Page")
        page = LandingPage.objects.create(name=name)
        return redirect("builder_edit_page", page_id=page.id)

    return render(request, "builder/new_page.html")

@csrf_exempt
def builder_edit_page(request, page_id):
    # Builder: edit page details and show recent AI logs
    page = LandingPage.objects.get(id=page_id)
    sections = page.sections.order_by("order")
    ai_logs = page.ai_recommendations.order_by("-created_at")[:20]  # latest 20

    return render(request, "builder/edit_page.html", {
        "page": page,
        "sections": sections,
        "ai_logs": ai_logs,
    })

@csrf_exempt
def builder_save_page(request, page_id):
    # Save page global CSS and section order via AJAX (JSON POST)
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    page = LandingPage.objects.get(id=page_id)

    data = json.loads(request.body)

    # Save global CSS
    page.global_css = data.get("global_css", "")
    page.save()

    # Save section order
    for sec in data.get("sections", []):
        section = LandingSection.objects.get(id=sec["id"])
        section.order = sec["order"]
        section.save()

    return JsonResponse({"status": "ok"})

def builder_new_section(request, page_id):
    # Builder: create a new section for the page
    page = LandingPage.objects.get(id=page_id)

    if request.method == "POST":
        key = request.POST.get("key")
        html = request.POST.get("html", "")
        css = request.POST.get("css", "")
        order = page.sections.count()

        LandingSection.objects.create(
            page=page,
            key=key,
            html=html,
            css=css,
            order=order,
        )
        return redirect("builder_edit_page", page_id=page_id)

    return render(request, "builder/edit_section.html", {
        "page": page,
        "section": None,
    })

def builder_edit_section(request, section_id):
    # Builder: edit an existing section
    section = LandingSection.objects.get(id=section_id)
    page = section.page

    if request.method == "POST":
        section.key = request.POST.get("key")
        section.html = request.POST.get("html", "")
        section.css = request.POST.get("css", "")
        section.save()
        return redirect("builder_edit_page", page_id=page.id)

    return render(request, "builder/edit_section.html", {
        "page": page,
        "section": section,
    })

def builder_delete_section(request, section_id):
    # Builder: delete a section and redirect back to page editor
    section = LandingSection.objects.get(id=section_id)
    page_id = section.page.id
    section.delete()
    return redirect("builder_edit_page", page_id=page_id)
