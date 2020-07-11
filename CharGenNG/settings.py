"""
Django settings for CharGenNG project.

Generated by 'django-admin startproject' using Django 3.0.5.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""

from __future__ import annotations
import os
import jinja2
# from jinja2 import Environment as Jinja2environment, DebugUndefined
from django.templatetags.static import static
from django.urls import reverse
import logging

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '&y)=#fc3wbkp7h$r&6ud*7pwmi^26+83^(bu*rfac7(q#l82#p'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

TESTING_MODE = False  # Custom attribute. This is set to True by runtests.py

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'DBInterface.apps.DBInterfaceConfig',
    'CGSandbox',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'CharGenNG.urls'

def urlarg(*args, **kwargs):
    """
    Used in jinja2 environment.
    Allows to use href = {{ urlarg(name) }} without adding "'s and escaping.
    """
    return jinja2.Markup('"' + reverse(*args, **kwargs) + '"')

def http_jinja_env(**options):
    env = jinja2.Environment(**options)
    env.globals.update({
        'static': static,
        'url': reverse,
        'urlarg': urlarg,
        'DEBUG_PRINT': (lambda x: str(x)+""),
    })

    class MyDebugUndefined(jinja2.DebugUndefined):
        def __str__(self):
            return "Undefined:" + super().__str__()
    logger = logging.getLogger('chargen.undefined_templates')
    env.undefined = jinja2.make_logging_undefined(logger=logger, base=MyDebugUndefined)
    return env

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,  # Changing this to False breaks the admin interface
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
    {
        'BACKEND': 'django.template.backends.jinja2.Jinja2',
        'APP_DIRS': False,
        'NAME': 'HTTPJinja2',
        'OPTIONS': {
            'environment': 'CharGenNG.settings.http_jinja_env',
            'context_processors': [
                # adds the following variables to templates
                # automatic (Jinja2-specific): csrf_input, csrf_token, request, cookie-name is csrftoken,
                # According to https://docs.djangoproject.com/en/3.0/topics/templates/ context processors are not really
                # in line with Jinja2's design (they are more of a workaround to django's default template engine's
                #  limitations). We use auth, though.
                # 'django.template.context_processors.debug',  # adds debug, sql_queries
                'django.contrib.auth.context_processors.auth',  # adds user, perms
            ],
        },
        'DIRS': [os.path.join(BASE_DIR, 'templates/http')]
    }
]

WSGI_APPLICATION = 'CharGenNG.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

AUTH_USER_MODEL = 'DBInterface.CGUser'

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    # {
    #     'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    # },
    # {
    #     'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    # },
    # {
    #    'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    # },
    # {
    #    'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    # },
]


# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'develop': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'simple',
        },
    },
    'formatters': {
      'simple': {
          'format': '{levelname} {message}',
          'style': '{',
      },
    },
    'loggers': {
        'chargen': {
            'handlers': ['develop'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = os.path.join(BASE_DIR, 'static/')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static/')]
