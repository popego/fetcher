from django.conf.urls.defaults import patterns, include, url

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$', 'fetcher.process.views.index', name='index'),
    url(r'^process/', include('fetcher.process.urls')),
    url(r'^login/$', 'django.contrib.auth.views.login', {'template_name':'auth/login.html'}),
    url(r'^logout/$', 'django.contrib.auth.views.logout', {'next_page': '/'}),
    # Examples:
    # url(r'^$', 'fetcher.views.home', name='home'),
    # url(r'^fetcher/', include('fetcher.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls))
)
