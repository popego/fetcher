"""
This module contains the behaviour of both the uploader and
writer module. It should be replaced with a django view later on.
"""

import logging

from optparse import OptionParser

from uploader import UploaderHandler
from writer import WriterHandler

class Fetcher(object):

    #TODO: Add handlers and proper logger configuration
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler("/mnt/fetcher/logs/fetcher.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    log.addHandler(fh)

    def __init__(self, queue_name, instance_amount, host="localhost"):
        self._queue_name = queue_name
        self._instance_amount = instance_amount
        self._host = host

    def fetch(self, seed_content):
        """
        Main method that should be called from outside
        """
        self.log.info("Initiating both uploader and writer handlers.")
        try:
            writer = WriterHandler(self._host, self._queue_name, seed_content=seed_content)
            uploader = UploaderHandler(self._instance_amount)

            self.log.info("Starting writer task.")
            writer.start()

            self.log.info("Starting uploader task.")
            instances_ids = uploader.start()
            return instances_ids
        except Exception, e:
            self.log.error("Couldn't process. e: %s", e)


if __name__ == "__main__":
    parser = OptionParser()
    parser.add_option("-n", '--host-name', dest="host_name", default="localhost")
    parser.add_option("-q", '--queue-name', dest="queue_name", default="test")
    parser.add_option("-s", "--seed-content", dest="seed_content", default="urls.txt")

    options, args = parser.parse_args()

    fetcher = Fetcher(options.queue_name)
    fetcher.fetch(options.seed_content)
