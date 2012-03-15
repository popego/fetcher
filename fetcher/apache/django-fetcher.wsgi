import os
import sys 
sys.stdout = sys.stderr

os.environ['DJANGO_SETTINGS_MODULE'] = 'fetcher.settings'

import django.core.handlers.wsgi
application = django.core.handlers.wsgi.WSGIHandler()
