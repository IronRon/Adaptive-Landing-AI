from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('track-interactions/', views.track_interactions, name='track_interactions'),
]
