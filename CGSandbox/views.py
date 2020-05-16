from django.shortcuts import render
from django.http import HttpResponse

# Create your views here.

def testview(request):
    return HttpResponse("Django running")

def jinjatestview(request):
    return render(request, "jinjatest.html", using="HTTPJinja2")
