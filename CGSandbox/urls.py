from django.urls import path
from django.contrib.auth.views import LoginView

from . import views

urlpatterns = [
    path("test", views.testview, name="CGTestview"),
    path("testjinja", views.jinjatestview, name="Jinjatest"),
    # path("login", LoginView.as_view()),
]
