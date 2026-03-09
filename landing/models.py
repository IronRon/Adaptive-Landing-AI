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

    Intent scores
    -------------
    When the session ends (``POST /end-session/``), the backend queries all
    :model:`landing.Event` rows for this session and computes engagement
    scores for each intent bucket from five per-section signals:

    1. **Clicks** in the section.
    2. **Hover time** on interactive elements in the section.
    3. **Dwell time** (how long the section was in the viewport).
    4. **CTA click** (binary — did they click a CTA in the section?).
    5. **CTA hover time** on CTA elements in the section.

    Each signal is normalised to 0..1 via a saturation function
    ``f(x) = x / (x + k)`` (no hard caps), and the five signals are
    averaged with **equal weights** to produce the intent score.

    * **price_intent_score** — engagement with the *pricing* section.
    * **service_intent_score** — engagement with the *services* section.
    * **trust_intent_score** — engagement with *testimonials* + *FAQ* +
      *trust bar* + *about* (all “can I trust this company?” content).
    * **location_intent_score** — engagement with the *locations* section
      (checking physical accessibility → serious purchase consideration).
    * **contact_intent_score** — engagement with the *contact* section
      (form focus/submit, clicking contact details → direct outreach intent).
    * **quick_scan_score** — 1.0 if the visitor scrolled far but dwelt
      little, indicating skimming rather than reading.
    * **primary_intent** — the argmax of the five intent scores (or
      ``"unknown"`` if none reaches the 0.1 threshold).

    These scores are persisted on the Session row so downstream consumers
    (bandit, analytics dashboard) can query them cheaply without replaying
    raw events.  See :func:`landing.utils.compute_session_intent_scores`
    for the full formula.
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
    visit_number = models.IntegerField(
        default=1,
        help_text="Which visit this is for the visitor (1 = first, 2 = second, …).",
    )

    # --- engagement aggregates (computed at session end) --------------------
    max_scroll_pct = models.IntegerField(
        default=0,
        help_text="Highest scroll-depth percentage reached during the session.",
    )
    engaged_time_ms = models.IntegerField(
        default=0,
        help_text="Total active time on page in milliseconds.",
    )
    cta_clicked = models.BooleanField(
        default=False,
        help_text="True if the visitor clicked any CTA element.",
    )
    conversion = models.BooleanField(
        default=False,
        help_text="Placeholder for future conversion tracking.",
    )

    # --- intent scores (0.0 – 1.0, computed from Event rows) ---------------
    price_intent_score = models.FloatField(
        default=0.0,
        help_text="Weighted score reflecting engagement with the pricing section.",
    )
    service_intent_score = models.FloatField(
        default=0.0,
        help_text="Weighted score reflecting engagement with the services section.",
    )
    trust_intent_score = models.FloatField(
        default=0.0,
        help_text="Weighted score reflecting engagement with testimonials, FAQ, trust bar, and about.",
    )
    location_intent_score = models.FloatField(
        default=0.0,
        help_text="Weighted score reflecting engagement with the locations section.",
    )
    contact_intent_score = models.FloatField(
        default=0.0,
        help_text="Weighted score reflecting engagement with the contact section.",
    )
    quick_scan_score = models.FloatField(
        default=0.0,
        help_text="1.0 if user scrolled far but dwelt little; 0.0 otherwise.",
    )
    primary_intent = models.CharField(
        max_length=32,
        default="unknown",
        help_text='Dominant intent bucket: "price", "service", "trust", "location", "contact", or "unknown".',
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["ended_at"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["primary_intent"]),
        ]

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


# ---------------------------------------------------------------------------
# Contextual bandit models
# ---------------------------------------------------------------------------

class BanditArm(models.Model):
    """
    A single bandit arm representing a page-layout variant.

    ``page_config`` is the JSON blob passed to the frontend's
    ``applyPageConfig()`` function.  Shape::

        {
            "compact": ["services"],
            "hide": [],
            "promote": "pricing",
            "variants": {"pricing": "highlight-plan-2"}
        }
    """

    arm_id = models.CharField(
        max_length=100,
        unique=True,
        help_text='Machine-readable key, e.g. "pricing_highlight_plan_2".',
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional human-readable label.",
    )
    page_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Config dict consumed by applyPageConfig on the frontend.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive arms are excluded from selection.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["arm_id"]

    def __str__(self):
        return self.arm_id


class BanditDecision(models.Model):
    """
    Records the bandit's choice for a single session.

    Only created for sessions where the bandit actually ran
    (visit_number >= 2).
    """

    session = models.OneToOneField(
        Session,
        on_delete=models.CASCADE,
        related_name="bandit_decision",
    )
    visitor = models.ForeignKey(
        Visitor,
        on_delete=models.CASCADE,
        related_name="bandit_decisions",
    )
    context_bucket = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text='Legacy bucket string (no longer used by the linear bandit).',
    )
    context_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Human-readable context snapshot used when making the decision.",
    )
    context_vector = models.JSONField(
        default=list,
        blank=True,
        help_text="Numeric feature vector (list of floats) used by the linear bandit.",
    )
    arm = models.ForeignKey(
        BanditArm,
        on_delete=models.CASCADE,
        related_name="decisions",
    )
    explore = models.BooleanField(
        help_text="True if this was an exploration pick (random).",
    )
    epsilon = models.FloatField(
        help_text="Epsilon value at decision time.",
    )
    reward = models.FloatField(
        null=True,
        blank=True,
        help_text="Filled in when the session ends (1.0 if CTA clicked, else 0.0).",
    )
    predicted_score = models.FloatField(
        null=True,
        blank=True,
        help_text="The model's predicted reward for the chosen arm at decision time.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["context_bucket"]),
        ]

    def __str__(self):
        return f"Decision session={self.session_id} arm={self.arm.arm_id}"


class BanditArmStat(models.Model):
    """
    Running statistics for a (context_bucket, arm) pair.

    DEPRECATED — kept for backward compatibility with existing data.
    The linear bandit now uses LinUCBParam instead.
    """

    context_bucket = models.CharField(max_length=100, db_index=True)
    arm = models.ForeignKey(
        BanditArm,
        on_delete=models.CASCADE,
        related_name="stats",
    )
    n = models.IntegerField(
        default=0,
        help_text="Number of times this arm was pulled in this bucket.",
    )
    sum_reward = models.FloatField(
        default=0.0,
        help_text="Cumulative reward for this arm in this bucket.",
    )
    mean_reward = models.FloatField(
        default=0.0,
        help_text="sum_reward / n  (cached for fast lookup).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["context_bucket", "arm"],
                name="unique_bucket_arm",
            ),
        ]
        indexes = [
            models.Index(fields=["context_bucket", "arm"]),
        ]

    def __str__(self):
        return f"Stat bucket={self.context_bucket} arm={self.arm.arm_id} n={self.n} mean={self.mean_reward:.3f}"


class LinUCBParam(models.Model):
    """
    Stored learning parameters for one bandit arm (linear contextual bandit).

    Each arm learns which kinds of visitors respond well to it. Instead of
    storing the final weights directly, we store two "compressed memory"
    fields that together remember everything needed to compute weights:

    A_matrix ("what I've seen")
        An 8×8 grid (features × features). Each time a visitor is shown
        this arm, their feature vector is multiplied by itself to produce
        an 8×8 grid of feature-pair combinations, and added to A_matrix.
        The diagonal tracks how much of each feature has been seen;
        the off-diagonal cells track which features appeared together
        (correlations), preventing the model from double-counting.
        Starts as an identity matrix (1s on diagonal) as a safe default
        that prevents division-by-zero and fades away as real data arrives.

    b_vector ("what worked")
        A list of 8 numbers. Each time a visitor clicks the CTA after
        seeing this arm (reward=1), their feature vector gets added to
        b_vector. Non-clicks (reward=0) contribute nothing. Over time
        b_vector accumulates a picture of "the kind of visitor this arm
        works well for."

    To get the arm's weights:  weights = A_matrix⁻¹ × b_vector
    Think of it as: "what worked" ÷ "what I've seen" = best prediction.
    """

    arm = models.OneToOneField(
        BanditArm,
        on_delete=models.CASCADE,
        related_name="linucb_param",
    )
    A_matrix = models.JSONField(
        help_text="8×8 grid tracking what visitors this arm has been shown to (feature combinations).",
    )
    b_vector = models.JSONField(
        help_text="8-number list tracking which visitor features led to CTA clicks for this arm.",
    )
    n = models.IntegerField(
        default=0,
        help_text="Total number of times this arm has been shown to a visitor.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "LinUCB Parameter"
        verbose_name_plural = "LinUCB Parameters"

    def __str__(self):
        return f"LinUCB arm={self.arm.arm_id} n={self.n}"
