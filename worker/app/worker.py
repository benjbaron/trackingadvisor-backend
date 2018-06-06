#!/usr/bin/env python
import sys
import pika
import time
import logging
from raven import Client

import process_user_traces

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)
connection = pika.BlockingConnection(pika.ConnectionParameters(host='colossus07'))
channel = connection.channel()

channel.queue_declare(queue='incoming_queue', durable=True)

client = Client('https://8f77b4f7e5a6410194f5826deaa3f9f4:74d1d77376ea4f7f8785cb192e62daeb@sentry.io/1207941')


def callback(ch, method, properties, body):
    # try:
    logging.info("Received %r" % body)

    start_ts = int(time.time())
    try:
        process_user_traces.process_all_tmp_user_traces(logging)
    except:
        print("error")
        client.captureException()
        sys.exit()

    end_ts = int(time.time())

    logging.info("Done in %s seconds" % (end_ts - start_ts,))
    ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_consume(callback,
                      queue='incoming_queue')

ts = int(time.time())
logging.info('Waiting for incoming messages...')

channel.start_consuming()
