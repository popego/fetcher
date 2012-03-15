import logging
import threading
import time

from optparse import OptionParser

import boto

from django.conf import settings
from fabric.api import local

AWS_ACCESS_KEY = ''
AWS_SECRET_KEY  = ''
AMI_ID = ''
KEY_NAME = ''
TYPE = 'm1.small'
SECURITY_GROUP = ''

IDENTITY = '/mnt/fetcher/id'
FABFILE_PATH = settings.PROJECT_ROOT + '/process/utils/fabfiles/run.py'

class UploadProcessException(Exception):
    def __init__(self, error):
        self._error = error

    def __str__(self):
        return "Could not upload - %s" % self._error


class UploaderHandler(object):
    """
    This class will handle everything that has to do with deploying and
    running the fetching core process content, as well as creating the necessary
    ec2 instances
    """

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler("/mnt/fetcher/logs/uploader.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    log.addHandler(fh)

    def __init__(self, instance_num=2):
        self.threads = []
        self.instance_ids = []
        self.instance_num = instance_num

        self.log.info("Connecting to EC2 server...")
        try:
            self.conn = boto.connect_ec2(AWS_ACCESS_KEY, AWS_SECRET_KEY)
        except Exception, e:
            self.log.error("Unable to connect to amazon. e: %s", e)
            self.stop()
            raise UploadProcessException(e)


    def start(self):
        """
        Main method that should be called from outside. It launches isntances
        and starts deploying threads
        """
        for i in range(0, self.instance_num):
            instance_dns, instance_id = self._launch_ec2_instance(i)
            self.log.info("Starting deploy process #%d", i)
            deployer = Deployer(i, instance_dns, instance_id, self.conn)
            deployer.start()
            self.threads.append(deployer)

        return self.instance_ids

    def _launch_ec2_instance(self, i):
        try:
            self.conn.run_instances(AMI_ID,
                                    key_name=KEY_NAME,
                                    instance_type=TYPE,
                                    security_groups=[SECURITY_GROUP])
            self.log.info("Started instance. Sleeping for a while.")
            time.sleep(60)

            #Get last reservation "[-1]", and the instance of that reservation
            while True:
                instance = self.conn.get_all_instances()[-1].instances[0]
                if instance.state == 'running':
                    #The instance may be running but not assigned with a dns yet
                    if instance.public_dns_name != '':
                        break
                self.log.info("Not ready yet...")
                time.sleep(10)

            instance.add_tag('Name', 'Fethcer_%d' % i)
            self.instance_ids.append(instance.id)

            return instance.public_dns_name, instance.id
        except Exception, e:
            self.log.error("Unable to start instance. e: %s", e)
            self.stop()
            raise UploadProcessException(e)

    def add_instance(self):
        self.log("Adding one more instance")
        num = len(self.instance_ids) + 1
        instance_dns = self._launch_ec2_instance(num)
        self.log.info("Adding instance #%d to fetching process", num)
        deployer = Deployer(num, instance_dns)
        deployer.start()
        self.threads.append(deployer)

    def stop(self):
        self.log.info("Terminating all #%d instances", len(self.instance_ids))
        self.conn.terminate_instances(instance_ids=self.instance_ids)
        self.conn.close()

    def stop_instances(self, instances):
        self.log.info("Terminating all #%d instances", len(instances))
        self.conn.terminate_instances(instance_ids=instances)
        self.conn.close()

    def wait(self):
        for thread in self.threads:
            thread.join()


class Deployer(threading.Thread):
    """
    Responsible of passing the core files to destination ip using fabric
    """

    log = logging.getLogger(__name__)

    def __init__(self, number, host, instance_id, conn):
        threading.Thread.__init__(self)

        self.number = number
        self.name = "Deployer#%d" % number
        self.host = host

        self.conn = conn
        self.instance_id = instance_id

    def run(self):
        self.log.info("%s - Letting amazon make its status check on the new instance. Sleeping 60s",
                      self.name)
        time.sleep(60)

        self.log.info("%s - starting remote script", self.name)
        fab = "/home/ubuntu/envs/fetcher/bin/fab "
        local(fab + "-i %s -f %s -u ubuntu -H %s start > /mnt/fetcher/logs/deployer/%s.log" %
                (IDENTITY, FABFILE_PATH, self.host, self.name))

        #Terminate instance
        self._terminate()

    def _terminate(self):
        self.log.info("%s - terminating amazon instance", self.name)
        self.conn.terminate_instances(instance_ids=[self.instance_id,])


if __name__ == "__main__":
    #Script usage should contain amount of threads to work with
    parser = OptionParser()
    parser.add_option('-i', '--instance-amount', dest="instance_amount", default=1)
    options, args = parser.parse_args()

    uploader = UploaderHandler(int(options.instance_amount))
    uploader.start()
