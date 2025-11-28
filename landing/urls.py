from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),

    # --- PAGE BUILDER ROUTES ---
    path('builder/', views.builder_index, name='builder_index'),
    path('builder/new/', views.builder_new_page, name='builder_new_page'),              # List page(s)
    path('builder/page/<int:page_id>/', views.builder_edit_page, name='builder_edit_page'),
    path('builder/page/<int:page_id>/save/', views.builder_save_page, name='builder_save_page'),

    path('builder/page/<int:page_id>/section/new/', views.builder_new_section, name='builder_new_section'),
    path('builder/section/<int:section_id>/edit/', views.builder_edit_section, name='builder_edit_section'),
    path('builder/section/<int:section_id>/delete/', views.builder_delete_section, name='builder_delete_section'),

    path('track-interactions/', views.track_interactions, name='track_interactions'),
    path('accept-cookies/', views.accept_cookies, name='accept_cookies'),
]
