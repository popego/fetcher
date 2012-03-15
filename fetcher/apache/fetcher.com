WSGIPythonHome /home/ubuntu/envs/fetcher

<VirtualHost *:80>
    ServerAdmin admin@fetcher.meaningtool.com
    ServerName fetcher.meaningtool.com
    ServerAlias fetcher.meaningtool.com

    LogLevel warn
    ErrorLog /var/log/apache2/fetcher/error.log
    CustomLog /var/log/apache2/fetcher/access.log combined

    WSGIDaemonProcess fetcher processes=2 maximum-requests=500 threads=25
    WSGIProcessGroup fetcher
    WSGIScriptAlias / /home/ubuntu/scripts/django-fetcher.wsgi
</VirtualHost>
