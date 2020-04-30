from django.shortcuts import render
from django.http import HttpResponse

# Create your views here.

def testview(request):
    return HttpResponse("Django running")
