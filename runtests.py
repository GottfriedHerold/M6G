#!/usr/bin/env python

import os
import sys
import django

from django.conf import settings as django_settings
from django.test.utils import get_runner

if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'CharGenNG.settings')
    import CharGenNG.settings as settings
    settings.TESTING_MODE = True
    settings.LOGGING = {}
    # May modify settings!
    django.setup()
    TestRunner = get_runner(django_settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(None)
    sys.exit(bool(failures))
