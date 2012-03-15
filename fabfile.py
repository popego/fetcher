#-*- coding: utf-8 -*-

"""
Fabric script which allows to update, install or deploy, and setup fetcher

Usage:
    fab -i *id* -u ubuntu -H *host* [target]

Where [target] can be either "setup" or "update"
"""


from fabric.api import sudo, put, cd, run

def setup():
    """
    In charge of configuring apache, deploying rabbitmq and creating the fetcher virtualenv
    """
    sudo("apt-get update")
    run("virtualenv --no-site-packages /home/ubuntu/envs/fetcher")
    run("mkdir -p /home/ubuntu/scripts/")

    #Installing postgresql
    sudo("apt-get install -y postgresql")

    #Installing rabbitmq
    run("wget 'http://www.rabbitmq.com/releases/rabbitmq-server/v2.7.1/rabbitmq-server_2.7.1-1_all.deb'")
    sudo("apt-get install -y erlang-nox")
    sudo("dpkg -i rabbitmq-server_2.7.1-1_all.deb")
    run("rm /home/ubuntu/rabbitmq-server_2.7.1-1_all.deb")

    #Create folder under mnt to contain ids, logs and files
    sudo("mkdir /mnt/fetcher")
    with cd("/mnt/fetcher"):
        sudo("mkdir logs")
        sudo("mkdir logs/deployer")
        sudo("mkdir results")
        sudo("chown www-data:www-data logs/deployer")
        sudo("chown www-data:www-data logs")
        sudo("chown www-data:www-data results")

    sudo("chown www-data:www-data /mnt/fetcher")

    _configure_apache()

def update():
    source = "source /home/ubuntu/envs/fetcher/bin/activate && "
    with cd("/home/ubuntu"):
        sudo(source + "easy_install -U fetcher")

    sudo("service apache2 restart")

def _configure_apache():
    sudo("apt-get --purge -y remove nginx")
    sudo("apt-get install -y apache2")
    sudo("apt-get install -y libapache2-mod-wsgi")
    #sudo("ln -s -f /etc/apache2/mods-available/rewrite.load '\
    #        '/etc/apache2/mods-enabled/rewrite.load")

    put("fetcher/apache/django-fetcher.wsgi", "/home/ubuntu/scripts/",
            use_sudo=True)
    put("fetcher/apache/fetcher.com", "/etc/apache2/sites-available/",
            use_sudo=True)
    sudo("mkdir -p /var/log/apache2/fetcher")
    sudo("chmod 775 /home/ubuntu/scripts/django-fetcher.wsgi")
    sudo("ln -s -f /etc/apache2/sites-available/fetcher.com "\
            "/etc/apache2/sites-enabled/fetcher.com")
    sudo("service apache2 restart")
