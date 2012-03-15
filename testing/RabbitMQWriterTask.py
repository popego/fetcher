import time

import pika
from pika.adapters import SelectConnection

pika.log.setup(color=True)

class Worker(object):
    def on_connected(self, connection):
        pika.log.info("Connected to server")
        connection.channel(self.on_channel_open)

    def on_channel_open(self, channel_):
        self.channel = channel_
        pika.log.info("Received channel")
        self.channel.queue_declare(queue="test", durable=True,
                              exclusive=False, auto_delete=False,
                              callback=self.on_queue_declared)

    def on_queue_declared(self, frame):
        pika.log.info("Queue declared!")
        for x in xrange(0,10):
            message = "Hello world #%i: %.8f" % (x, time.time())
            pika.log.info("Sending message: %s" % message)
            self.channel.basic_publish(exchange='',
                                  routing_key='test',
                                  body=message,
                                  properties=pika.BasicProperties(
                                  content_type="text/plain",
                                  delivery_mode=1))
        self.connection.close()




if __name__ == "__main__":
    worker = Worker()
    parameters = pika.ConnectionParameters('localhost')
    worker.connection = SelectConnection(parameters, worker.on_connected)
    try:
        worker.connection.ioloop.start()
    except KeyboardInterrupt:
       worker.connection.close()
