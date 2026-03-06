"""Admin registrations for the landing app models."""

from django.contrib import admin

from .models import (
    BanditArm,
    BanditArmStat,
    BanditDecision,
    Event,
    LandingPage,
    LandingSection,
    LinUCBParam,
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
        "visit_number",
        "started_at",
        "ended_at",
        "is_active",
        "primary_intent",
        "price_intent_score",
        "service_intent_score",
        "trust_intent_score",
        "location_intent_score",
        "contact_intent_score",
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
    list_display = ("arm_id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("arm_id", "name")
    readonly_fields = ("created_at",)


@admin.register(BanditDecision)
class BanditDecisionAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "visitor",
        "arm",
        "explore",
        "epsilon",
        "reward",
        "created_at",
    )
    list_filter = ("explore",)
    search_fields = ("session__session_id", "visitor__cookie_id", "arm__arm_id")
    readonly_fields = ("created_at",)


@admin.register(BanditArmStat)
class BanditArmStatAdmin(admin.ModelAdmin):
    list_display = ("context_bucket", "arm", "n", "sum_reward", "mean_reward", "updated_at")
    list_filter = ("context_bucket",)
    search_fields = ("context_bucket", "arm__arm_id")
    readonly_fields = ("updated_at",)


@admin.register(LandingPage)
class LandingPageAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")


@admin.register(LandingSection)
class LandingSectionAdmin(admin.ModelAdmin):
    list_display = ("key", "page", "order", "created_at")


@admin.register(LinUCBParam)
class LinUCBParamAdmin(admin.ModelAdmin):
    list_display = ("arm", "n", "updated_at")
    search_fields = ("arm__arm_id",)
    readonly_fields = ("updated_at",)
