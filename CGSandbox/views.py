from django.shortcuts import render
from django.http import HttpResponse
import logging

# Create your views here.

def testview(request):
    return HttpResponse("Django running")

def jinjatestview(request):
    return render(request, "base.html", using="HTTPJinja2")
