from django.shortcuts import render
from django.http import HttpResponse
import logging
from django.template import RequestContext

# logger = logging.getLogger('chargen')
# logger.info('Initialized logger')
# Create your views here.

def testview(request):
    return HttpResponse("Django running")

def jinjatestview(request):
    context = RequestContext(request)
    return render(request, "base.html", using="HTTPJinja2", context={})
