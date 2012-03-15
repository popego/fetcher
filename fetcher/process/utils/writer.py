import threading
import logging
import Queue
import pickle
import os

from optparse import OptionParser

import pika
from pika.adapters import SelectConnection
from crawle import RequestResponse

WRITER_THREADS=5

class WriterHandler(object):
    """
    Core process class in charge of populate the rabbitmq and decide
    whether to use a seed file or string data from uploaded files
    """

    #TODO: Add handlers and proper logger configuration
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler("/mnt/fetcher/logs/writer.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    log.addHandler(fh)


    def __init__(self, host, queue_name, seed_content=None):
        self.threads = []
        self.outgoing_queue = Queue.Queue()
        self.urls = ''

        if seed_content:
            if os.path.isfile(seed_content):
               self.log.info("Seed file provided, passing urls to memory")
               fp = open(seed_content, 'r')
               #File should contain urls with '\n'
               self.urls = fp.read().split()
            else:
               self.log.info("Seed file not found, processing raw_data")
               self.urls = seed_content.split()

        if not self.urls:
            raise Exception("No urls provided")

        for url in self.urls:
           if not url.startswith('http'):
               url = "http://%s" % url

           self.log.debug("url append. %s", url)
           self.outgoing_queue.put(url)

        for _ in range(0, WRITER_THREADS):
            self.threads.append(RabbitMQWriterTask(host, queue_name,
                                                   self.outgoing_queue))

    def start(self):
        """
        Main method that should be called from outside
        """
        try:
            self.log.info("Starting %d writer threads...", len(self.threads))

            for thread in self.threads:
                thread.start()
        except Exception, e:
            self.log.info("Exception while trying to initiate writer threads. e: %s", e)
            self.stop()

    def stop(self):
        self.log.info("Stopping %d writer threads...", len(self.threads))
        for thread in self.threads:
            thread.should_work = False


class RabbitMQWriterTask(threading.Thread):
    """
    RabbitMQ event driven writer class using pika client
    docs: http://pika.github.com/index.html
    """

    #TODO: Add handlers and proper logger configuration
    log = logging.getLogger(__name__)

    def __init__(self, host, queue_name, outgoing_queue):
        threading.Thread.__init__(self)

        self.queue_name = queue_name
        self.outgoing_queue = outgoing_queue

        self.should_work = True

        self.log.info("Establishing connection to RabbitMQ")
        self.log.info("Rabbit Host: %s, Queue name: %s", host, queue_name)

        self.parameters = pika.ConnectionParameters(host)
        self.connection = SelectConnection(self.parameters, self.on_connected)


    def run(self):
        try:
            self.connection.ioloop.start()
        except Queue.Empty, e:
            self.log.info("Writer finished.")
        except Exception, e:
            self.log.error("Exception while writing rabbit messages. e: %s", e)


    def on_connected(self, connection):
        self.log.debug("Connected to server")
        connection.channel(self.on_channel_open)


    def on_channel_open(self, channel_):
        self.log.debug("Channel received")
        self.channel = channel_
        self.channel.queue_declare(queue=self.queue_name, durable=True,
                                   exclusive=False, auto_delete=False,
                                   callback=self.on_queue_declared)


    def on_queue_declared(self, frame):
        """
        This method publishes pickled serialized crawle.Response objects
        directly in the rabbit queue, with the url passed through the outgoing_queue
        """

        self.log.debug("queue declared")
        try:
            while self.should_work:
                url = self.outgoing_queue.get(timeout=1)
                response = RequestResponse(url)
                response_str = pickle.dumps(response)
                self.log.debug("Sending message to RabbitMQ")
                self.channel.basic_publish(exchange='',
                                           routing_key=self.queue_name,
                                           body=response_str,
                                           properties=pika.BasicProperties(
                                           content_type="text/plain",
                                           delivery_mode=1))
            self.log.info("Writer Task should not process more messages")
            self.connection.close()
        except Queue.Empty, e:
            raise Queue.Empty(e)
        except Exception, e:
            raise Exception(e)



if __name__ == "__main__":
    #In script mode usage, you may want to pass a seed file as string to the WriterHandler class
    parser = OptionParser()
    parser.add_option('-s', '--seed-file', dest="seed_file", default='urls.txt',
                      help="Seed file in which all urls should be followed by new line")
    parser.add_option('-q', '--queue-name', dest="queue_name", default="test_queue",
                      help="Queue name to be used or created if there isn't one")
    parser.add_option('-n', '--host-name', dest="host_name", default="localhost")

    options, args = parser.parse_args()

    writer = WriterHandler(options.host_name, options.queue_name, seed_content=options.seed_file)
    writer.start()
