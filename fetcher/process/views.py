import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponseRedirect

from forms import UploadedFileForm
from models import Request

from utils.fetcher import Fetcher
from utils.uploader import UploaderHandler

@login_required
def index(request):
    form = UploadedFileForm()
    return render_to_response('index.html', {'form': form},
                              context_instance=RequestContext(request))

@login_required
def process(request):
    if request.method == 'POST':
        form = UploadedFileForm(request.POST, request.FILES)
        if form.is_valid():
            motive = form.cleaned_data["motive"]
            instances_used = form.cleaned_data["instance_num"]
            seed_content = request.FILES['file'].read()


            fetcher = Fetcher("fetch_queue", instances_used)
            instances_ids = fetcher.fetch(seed_content)

            #Could not parse directly from form because of the file
            req_model = Request()
            req_model.motive = motive
            req_model.instances_used = instances_used
            req_model.user = request.user
            req_model.content = seed_content
            req_model.instances_ids = json.dumps(instances_ids)
            req_model.save()

            return HttpResponseRedirect("/process/%d" % req_model.id)

@login_required
def show_process(request, job_id):
    req_model = Request.objects.get(pk=job_id)

    return render_to_response('process.html',
                             {'instance_num': req_model.instances_used,
                              'seed_content': req_model.content,
                              'job_id': req_model.id},
                              context_instance=RequestContext(request))

@login_required
def add_machine(request, job_id):
    #uploader = UploaderHandler()
    #uploader.add_instance()

    req_model = Request.objects.order_by('-created_at')[0:1].get()
    req_model.instances_used += 1
    req_model.save()

    return HttpResponseRedirect('/process/%d' % req_model.id)

@login_required
def stop(request, job_id):
    job = Request.objects.get(pk=job_id)
    uploader = UploaderHandler()

    instances_ids = json.loads(job.instances_ids)
    uploader.stop_instances(instances_ids)
    return HttpResponseRedirect('/')
