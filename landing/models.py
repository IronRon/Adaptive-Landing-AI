# Database models for visitors, sessions, interactions, bandit arms, pages, sections, and AI logs.

from django.db import models
import uuid

# A site visitor tracked via a cookie UUID
class Visitor(models.Model):
    cookie_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.cookie_id)


# A browsing session belonging to a Visitor
class Session(models.Model):
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name='sessions')
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)  # browser info
    referrer = models.URLField(null=True, blank=True)     # referring URL
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.visitor.cookie_id} - {self.session_id}"


# Stored user interactions (click, scroll, etc.) for analytics and bandit signals
class Interaction(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='interactions')
    event_type = models.CharField(max_length=50)  # e.g. "click", "scroll"
    element = models.CharField(max_length=255, null=True, blank=True)  # element identifier or section
    timestamp = models.DateTimeField(auto_now_add=True)
    x = models.FloatField(null=True, blank=True)  # optional click X coordinate
    y = models.FloatField(null=True, blank=True)  # optional click Y coordinate
    additional_data = models.JSONField(default=dict, blank=True)  # extra event details

    def __str__(self):
        return f"{self.event_type} - {self.element}"


# Simple bandit arm tracking per section for global scoring
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
