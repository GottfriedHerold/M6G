from django.shortcuts import render
from django.http import HttpResponse, HttpRequest
import logging
from django.template import RequestContext

logger = logging.getLogger('chargen')
# logger.info('Initialized logger')
# Create your views here.

def testview(request):
    return HttpResponse("Django running")

def jinjatestview(request: HttpRequest):
    if request.method=="POST":
        logger.critical("%s", request.POST)
    return render(request, "jinjatest.html", using="HTTPJinja2", context={})
