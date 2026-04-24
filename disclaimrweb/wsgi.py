"""WSGI entry point for the disclaimrNG web administration."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "disclaimrweb.settings")

application = get_wsgi_application()
