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

class CharGenView(View):

    template = "main.html"

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
    #   Process Login

    def post(self, request: HttpRequest, *args, **kwargs):
        context = {}
        if request.POST.get('form_id') == "login":
            # Using Django's AuthenticationForm is a pain. It's easier to do everything yourself.
            username = request.POST.get("username")
            password = request.POST.get("password")
            if not username:
                context['login_fail'] = True
                login_logger.critical("Login with empty username")  # can only happen with form tampering.
            elif not password:
                context['login_fail'] = True
                login_logger.critical("Login with empty password")  # can only happen with form tampering.
            elif len(username) > CG_USERNAME_MAX_LENGTH or len(password) > 254:
                context['login_fail'] = True
                login_logger.critical("Login with too long pw/username")
            else:
                new_user: CGUser = auth.authenticate(request, username=username, password=password)
                if new_user is not None and new_user.is_authenticated:
                    login_logger.info("User %s authenticated successfully", str(new_user))
                    auth.login(request, new_user)
                    login_logger.info("User %s logged in", str(new_user))
                    return HttpResponseRedirect(request.path)
                else:  # credentials were passed, but they were invalid.
                    context['login_fail'] = True
                    login_logger.warning("Failed login attempt for username %s", username)
        return render(request, self.template, context=context, using="HTTPJinja2")
        pass


# def mainview(request):
#     return render(request, "main.html", using="HTTPJinja2")

def logoutview(request: HttpRequest):
    login_logger.info("Logout: user %s", str(request.user))
    auth.logout(request)
    return HttpResponseRedirect(reverse("landing"))
