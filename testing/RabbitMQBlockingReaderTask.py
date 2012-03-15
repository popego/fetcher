import threading

import pika
from pika.adapters import BlockingConnection

pika.log.setup(color=True)

class BlockingReader(object):
    def __init__(self, host, queue):

        self.queue = queue
        self.parameters = pika.ConnectionParameters(host)
        pika.log.info("Establishing connection")
        self.connection = BlockingConnection(self.parameters)

        pika.log.info("About to declare queue")

        pika.log.info("Queue declared")

    def read(self, channel):
        pika.log.info("Reading single message")
        method, header, body = channel.basic_get(queue=self.queue)
        pika.log.info("Message received!")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def create_channel(self):
        channel = self.connection.channel()
        return channel

    def stop(self):
        self.connection.close()

class Jodeme(threading.Thread):
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue

    def run(self):
        new_channel = self.queue.create_channel()
        while self.queue.connection.is_open:
            self.queue.read(new_channel)


if __name__ == "__main__":
    threads = []
    reader = BlockingReader('ec2-23-20-111-92.compute-1.amazonaws.com', 'test1')
    for num in range(0,3):
        threads.append(Jodeme(reader))

    for thread in threads:
        thread.start()
