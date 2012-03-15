from django import forms

class UploadedFileForm(forms.Form):
    instance_num =  forms.IntegerField()
    motive = forms.CharField(max_length=100)
    file = forms.FileField()
