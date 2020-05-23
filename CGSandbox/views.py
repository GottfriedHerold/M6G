from django.shortcuts import render
from django.http import HttpResponse
import logging

# logger = logging.getLogger('chargen')
# logger.info('Initialized logger')
# Create your views here.

def testview(request):
    return HttpResponse("Django running")

def jinjatestview(request):
    # logger = logging.getLogger('chargen')
    # logger.info(request.__dict__['environ'])
    return render(request, "base.html", using="HTTPJinja2")
