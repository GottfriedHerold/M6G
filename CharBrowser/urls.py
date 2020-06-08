from django.urls import path, reverse
from django.contrib.auth.views import LoginView, LogoutView


from . import views

urlpatterns = [
#    path("test", views.testview, name="CGTestview"),
#    path("testjinja", views.jinjatestview, name="Jinjatest"),
    # path("login", LoginView.as_view()),
    # path("login", views.loginview, name="Login"),
    path("", views.CharGenView.as_view(), name="landing"),
    path("logout", views.logoutview, name="logout")
]
