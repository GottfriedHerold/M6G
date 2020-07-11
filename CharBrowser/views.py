from __future__ import annotations
from django.shortcuts import render
from django.views import View
from django.http import HttpResponse, HttpRequest, HttpResponseRedirect
import django.contrib.auth as auth
from django.urls import reverse
# from django.contrib.auth.forms import AuthenticationForm
# Create your views here.
from DBInterface.models import CGUser, CG_USERNAME_MAX_LENGTH
import logging
logger = logging.getLogger('chargen.browser')
login_logger = logging.getLogger('chargen.browser.logins')

# def loginview(request):
#    return render(request, "login.html", using="HTTPJinja2")

#TODO: Control various processing by class variables

class CharGenView(View):

    template = "main.html"

    @staticmethod
    def process_authentication_attempt(self, request: HttpRequest) -> bool:
        """
        Processes an authentication attempt with username/password in request.POST.
        If successful, logs the user in and returns True.
        otherwise, returns False.
        Note: If this function returns True, request.user can not be relied upon. It is recommended
        to immediately redirect to a fresh url.
        """
        # Using Django's AuthenticationForm is a pain. After spending hours to figure out things and getting it to work
        # (albeit ugly), I could not figure out how to make it look nice.
        # It was 10x faster to ditch it and do everything myself.
        username = request.POST.get("username")
        password = request.POST.get("password")
        if not username:
            login_logger.critical("Login with empty username")  # can only happen with form tampering.
            return False
        if not password:
            login_logger.critical("Login with empty password")  # can only happen with form tampering.
            return False
        if len(username) > CG_USERNAME_MAX_LENGTH or len(password) > 254:
            login_logger.critical("Login with too long pw/username")
            return False
        new_user: CGUser = auth.authenticate(request, username=username, password=password)
        if new_user is not None and new_user.is_authenticated and new_user.is_active:
            login_logger.info("User %s authenticated successfully", str(new_user))
            auth.login(request, new_user)
            login_logger.info("User %s logged in", str(new_user))
            return True
        else:  # credentials were passed, but they were invalid.
            login_logger.warning("Failed login attempt for username %s", username)
            return False



    def get(self, request: HttpRequest, *args, **kwargs):
        context = {}
        user: CGUser = request.user
        # TODO:
        # determine char / charversion that was requested
        # Verify permissions
        # Create CharVersion object
        # Create Login/Logout form
        # Create extra context (subclassed)
        # Render
        # if not user.is_authenticated:
        #     context['login_form'] = AuthenticationForm(request)

        return render(request, self.template, context=context, using="HTTPJinja2")

    # TODO:
    # Determine Char / CharVersion
    # Check permissions
    # Create CharVersion object
    # Determine Request type
    # Process Login

    def post(self, request: HttpRequest, *args, **kwargs):
        context = {}
        if request.POST.get('form_id') == "login":
            if self.process_authentication_attempt(request):
                return HttpResponseRedirect(request.path)
            else:
                context['login_fail'] = True  # will display an error message
        return render(request, self.template, context=context, using="HTTPJinja2")
        pass


# def mainview(request):
#     return render(request, "main.html", using="HTTPJinja2")

def logoutview(request: HttpRequest):
    login_logger.info("Logout: user %s", str(request.user))
    auth.logout(request)
    return HttpResponseRedirect(reverse("landing"))
