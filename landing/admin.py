"""Admin registrations for the landing app models."""

from django.contrib import admin

from .models import (
    BanditArm,
    Event,
    LandingPage,
    LandingSection,
    Session,
    Visitor,
)


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("cookie_id", "created_at", "last_seen")
    search_fields = ("cookie_id",)
    readonly_fields = ("cookie_id", "created_at", "last_seen")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        "session_id",
        "visitor",
        "started_at",
        "ended_at",
        "is_active",
        "primary_intent",
        "price_intent_score",
        "service_intent_score",
        "trust_intent_score",
        "cta_clicked",
        "max_scroll_pct",
        "engaged_time_ms",
        "quick_scan_score",
    )
    list_filter = ("is_active", "primary_intent", "cta_clicked")
    search_fields = ("session_id", "visitor__cookie_id")
    readonly_fields = ("session_id", "started_at")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "section", "element", "is_cta", "timestamp", "session")
    list_filter = ("event_type", "is_cta")
    search_fields = ("event_type", "section", "element")
    readonly_fields = ("created_at",)


@admin.register(BanditArm)
class BanditArmAdmin(admin.ModelAdmin):
    list_display = ("section", "pulls", "reward")


@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")


@admin.register(LandingSection)
class LandingSectionAdmin(admin.ModelAdmin):
    list_display = ("key", "page", "order", "created_at")
