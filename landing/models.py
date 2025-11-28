from django.db import models
import uuid

class Visitor(models.Model):
    cookie_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.cookie_id)


class Session(models.Model):
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name='sessions')
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    referrer = models.URLField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.visitor.cookie_id} - {self.session_id}"


class Interaction(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='interactions')
    event_type = models.CharField(max_length=50)  # click, scroll, hover, etc.
    element = models.CharField(max_length=255, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    x = models.FloatField(null=True, blank=True)  # optional for click position
    y = models.FloatField(null=True, blank=True)
    additional_data = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.event_type} - {self.element}"


class BanditArm(models.Model):
    section = models.CharField(max_length=50, unique=True)
    pulls = models.IntegerField(default=0)    # number of times selected
    reward = models.FloatField(default=0.0)   # cumulative reward

    def __str__(self):
        return f"{self.section}: pulls={self.pulls}, reward={self.reward}"
    
class LandingPage(models.Model):
    name = models.CharField(max_length=255)
    global_css = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class LandingSection(models.Model):
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="sections")
    key = models.SlugField()       # e.g. "services", "pricing", etc.
    order = models.IntegerField(default=0)
    html = models.TextField()      # raw HTML snippet
    css = models.TextField(blank=True)  
    created_at = models.DateTimeField(auto_now_add=True)
