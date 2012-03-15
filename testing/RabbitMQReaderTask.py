import pika
from pika.adapters import SelectConnection

pika.log.setup(color=True)

class Reader(object):
    def __init__(self, host, queue):
        pika.log.info("Creating object")

        self.queue = queue
        self.parameters = pika.ConnectionParameters(host)
        self.connection = SelectConnection(self.parameters, self.on_connected)

    def on_connected(self, connection):
        pika.log.info("Opening channel")
        connection.channel(self.on_open_channel)

    def on_open_channel(self, channel_):
        pika.log.info("Channel opened")
        self.channel = channel_
        self.channel.queue_declare(queue=self.queue, durable=True,
                                   exclusive=False, auto_delete=False,
                                   callback=self.on_queue_declared)

    def on_queue_declared(self, frame):
        pika.log.info("Queue declared")
        self.channel.basic_consume(self.on_get, queue=self.queue)

    def on_get(self, channel, meth_frame, head_frame, body):
        pika.log.info("message received")
        pika.log.info(body)

if __name__ == "__main__":
    reader = Reader("ec2-23-20-111-92.compute-1.amazonaws.com", "test_queue")
    try:
        reader.connection.ioloop.start()
    except KeyboardInterrupt:
        reader.connection.close()


