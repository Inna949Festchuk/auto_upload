from django.urls import path

from core import views

urlpatterns = [
    path("api/token/", views.TokenView.as_view()),
    path("api/oauth-url/", views.OAuthUrlView.as_view()),
    path("api/disk/browse/", views.BrowseView.as_view()),
    path("api/tasks/", views.TaskListView.as_view()),
    path("api/tasks/<uuid:pk>/", views.TaskDetailView.as_view()),
    path("api/tasks/<uuid:pk>/cancel/", views.TaskCancelView.as_view()),
]
