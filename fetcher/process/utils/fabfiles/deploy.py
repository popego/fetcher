"""
Simple Script which deploys the main application into production

Usage:
    fab -i ~/.ssh/amazon_id -u ubuntu -f deploy.py -H *Host de amazon* start

IMPORTANT:
    When deploying, all constant values of the uploader should be modified in production
    as well as the host name of the crawle rabbitmq queue
"""

from fabric.api import run, put, sudo

def start():
    _copy_files()
    _install_dependences()
    _start_application()

def _copy_files():
    put("../src", "/home/ubuntu/")
    put("run.py", "/home/ubuntu/src/")
    put("../thirdparty/*", "/home/ubuntu/")
    put("~/.ssh/id_mtengine", "/home/ubuntu/src/")

def _install_dependences():
    run("virtualenv --no-site-packages fetcher")
    source = "source ~/fetcher/bin/activate && "
    run(source + "easy_install lxml")
    run(source + "easy_install pika")
    run(source + "easy_install fabric")
    run(source + "pip install boto==2.2.2")

    sudo("aptitude install erlang-nox")
    sudo("dpkg -i rabbitmq-server_2.7.1-1_all.deb")

def _start_application():
    """
    For security issues, application should be configured and
    started inside the main amazon instance
    """
    pass
