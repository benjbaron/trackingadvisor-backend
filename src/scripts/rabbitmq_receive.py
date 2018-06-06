#!/usr/bin/env python
import pika
import time

connection = pika.BlockingConnection(pika.ConnectionParameters(host='colossus07'))
channel = connection.channel()


channel.queue_declare(queue='hello')


def callback(ch, method, properties, body):
    print(" [x] Received %r (%s)" % (body, body.count(b'o')))
    time.sleep(body.count(b'o'))
    print(" [x] Done")


channel.basic_consume(callback,
                      queue='hello',
                      no_ack=True)

print(' [*] Waiting for messages. To exit press CTRL+C')
channel.start_consuming()
