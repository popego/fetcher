from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('fetcher.process.views',
    url(r'^$', 'process', name='process'),
    url(r'^(?P<job_id>\d+)$', 'show_process', name="status"),
    url(r'^(?P<job_id>\d+)/add_machine/$', 'add_machine', name="add"),
    url(r'^(?P<job_id>\d+)/stop/$', 'stop', name="stop"),
    )
