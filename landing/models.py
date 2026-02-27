"""
Database models for the tracking & analytics layer.

Visitor  – long-lived cookie-based identity (UUID).
Session  – one page-load / browsing session per visitor.
Event    – every tracked interaction inside a session.

Other models (BanditArm, LandingPage, LandingSection, AIRecommendation)
support the page builder and future contextual-bandit features.
"""

from django.db import models
import uuid


# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------

class Visitor(models.Model):
    """
    A unique site visitor identified by a long-lived cookie UUID.

    The cookie (``visitor_id``) is set when the user accepts cookies and
    persists for one year so we can recognise returning visitors.
    """

    cookie_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Stored in the visitor_id cookie on the client.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Visitor {self.cookie_id}"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class Session(models.Model):
    """
    A single visit session belonging to a :model:`landing.Visitor`.

    A new session is created every time the visitor loads the landing page
    (after cookie consent has been given).  Old active sessions are closed
    automatically when a new one starts.
    """

    visitor = models.ForeignKey(
        Visitor,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    session_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Passed to the frontend and sent back with every event batch.",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    referrer = models.URLField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Session {self.session_id} (visitor {self.visitor.cookie_id})"


# ---------------------------------------------------------------------------
# Event  (was "Interaction" — renamed for clarity)
# ---------------------------------------------------------------------------

class Event(models.Model):
    """
    A single tracked interaction event within a :model:`landing.Session`.

    Commonly-queried fields (``event_type``, ``section``, ``element``,
    ``is_cta``, ``duration_ms``) are stored as real columns for fast
    filtering.  Everything else the frontend sends is kept in the
    ``metadata`` JSONField so nothing is lost.

    Frontend event types
    --------------------
    page_view, click, hover, section_view, section_dwell,
    scroll_depth, time_on_page, form_focus, form_submit
    """

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="events",
    )

    # --- core fields -------------------------------------------------------
    event_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="E.g. click, hover, section_view, scroll_depth …",
    )
    timestamp = models.DateTimeField(
        help_text="Client-side event timestamp (ISO 8601 from JS Date).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    url = models.CharField(max_length=500, blank=True, default="")

    # --- context fields (nullable — not every event has them) ---------------
    section = models.CharField(max_length=100, blank=True, default="")
    element = models.CharField(max_length=255, blank=True, default="")
    is_cta = models.BooleanField(null=True, default=None)
    duration_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Duration in ms (hover, section_dwell, time_on_page).",
    )

    # --- catch-all for extra payload fields ---------------------------------
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="tag, text, depth, seconds, read, form_id, field, referrer …",
    )

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["session", "event_type"]),
            models.Index(fields=["section"]),
        ]

    def __str__(self):
        label = self.section or self.element or ""
        return f"{self.event_type} {label}".strip()


# ---------------------------------------------------------------------------
# Bandit arm (global section scoring — used later by contextual bandit)
# ---------------------------------------------------------------------------

class BanditArm(models.Model):
    section = models.CharField(max_length=50, unique=True)
    pulls = models.IntegerField(default=0)    # times the arm was chosen
    reward = models.FloatField(default=0.0)   # cumulative reward

    def __str__(self):
        return f"{self.section}: pulls={self.pulls}, reward={self.reward}"
    
# Landing page container with optional global CSS
class LandingPage(models.Model):
    name = models.CharField(max_length=255)
    global_css = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

# Individual page sections (order, HTML, and CSS)
class LandingSection(models.Model):
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="sections")
    key = models.SlugField()       # unique key like "services" or "pricing"
    order = models.IntegerField(default=0)
    html = models.TextField()      # HTML snippet for rendering
    css = models.TextField(blank=True)  
    created_at = models.DateTimeField(auto_now_add=True)

# Store AI recommendation responses for auditing/debugging
class AIRecommendation(models.Model):
    page = models.ForeignKey(
        LandingPage,
        on_delete=models.CASCADE,
        related_name="ai_recommendations"
    )
    visitor = models.ForeignKey(
        Visitor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_recommendations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    response_json = models.JSONField()
