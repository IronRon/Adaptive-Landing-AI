from django.shortcuts import redirect, render
from django.utils import timezone
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from collections import Counter
import uuid
from .models import AIRecommendation, LandingPage, LandingSection, Visitor, Session, Interaction
from .bandit import SectionBandit
from .utils import get_user_section_scores, combine_scores
from .ai_llm import generate_llm_recommendations
from django.core.exceptions import ValidationError

def generate_recommendations(visitor, sections, combined_css, page):
    # 1. Load valid sections (arms)
    default_layout = [sec.key for sec in sections]
    assets = {
        sec.key: {
            "html": sec.html,
        }
        for sec in sections
    }

    # 2. Global scores from bandit
    bandit = SectionBandit()
    global_scores = bandit.get_global_scores()

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
    css_parts = [page.global_css]

    for sec in page.sections.order_by("order"):
        if sec.css.strip():
            css_parts.append(sec.css)

    return "\n\n".join(css_parts)


def landing_page(request):
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
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)
    
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    session_id = data.get("session_id")
    if not session_id:
        return JsonResponse({"error": "Missing session_id"}, status=400)
    
    try:
        session = Session.objects.get(session_id=session_id)
    except (Session.DoesNotExist, ValidationError, ValueError, TypeError):
        return JsonResponse({"error": "Invalid session_id"}, status=400)
    
    events = data.get("events", [])
    for e in events:
        Interaction.objects.create(
            session=session,
            event_type=e.get("event_type"),
            element=e.get("element"),
            additional_data=e.get("additional_data", {}),
        )

    return JsonResponse({"status": "success"})

@csrf_exempt
def accept_cookies(request):
    # Called by JS only when user accepts the popup
    visitor = Visitor.objects.create()
    cookie_id = str(visitor.cookie_id)

    # Create a new session
    session = Session.objects.create(
        visitor=visitor,
        user_agent=request.META.get("HTTP_USER_AGENT", "") or None,
        referrer=request.META.get("HTTP_REFERER", "") or None
    )

    # Return session id so client can start tracking immediately (and set cookie)
    response = JsonResponse({"status": "accepted", "session_id": str(session.session_id)})
    # set cookie for future requests;
    response.set_cookie("visitor_id", cookie_id, max_age=60*60*24*365)
    return response


def builder_index(request):
    pages = LandingPage.objects.all()
    return render(request, "builder/index.html", {"pages": pages})

def builder_new_page(request):
    if request.method == "POST":
        name = request.POST.get("name", "My Landing Page")
        page = LandingPage.objects.create(name=name)
        return redirect("builder_edit_page", page_id=page.id)

    return render(request, "builder/new_page.html")

@csrf_exempt
def builder_edit_page(request, page_id):
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
    section = LandingSection.objects.get(id=section_id)
    page_id = section.page.id
    section.delete()
    return redirect("builder_edit_page", page_id=page_id)
