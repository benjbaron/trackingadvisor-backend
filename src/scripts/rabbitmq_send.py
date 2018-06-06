#!/usr/bin/env python
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters('colossus07'))
channel = connection.channel()

channel.queue_declare(queue='incoming_queue', durable=True)

channel.basic_publish(exchange='',
                      routing_key='incoming_queue',
                      body='Hello World!',
                      properties=pika.BasicProperties(
                          delivery_mode=2,  # make message persistent
                      ))

print(" [x] Sent 'Hello World!'")

connection.close()
