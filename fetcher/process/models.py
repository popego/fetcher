from django.db import models
from django.contrib.auth.models import User

class Error(models.Model):
    url = models.CharField(max_length=100)
    error = models.TextField()

    def __unicode__(self):
        return self.url

    class Meta:
        db_table = "error"
        verbose_name = "error"
        verbose_name_plural = "errors"

class Request(models.Model):
    user = models.ForeignKey(User)
    motive = models.CharField(max_length=100)
    instances_used = models.IntegerField()
    content = models.TextField()
    created_at = models.DateTimeField(auto_now=True)

    #Lists of amazon istances saved in JSON format
    instances_ids = models.TextField()

    def __unicode__(self):
        return self.name

    class Meta:
        db_table = "request"
        verbose_name = "request"
        verbose_name_plural = "requests"
