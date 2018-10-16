#!/usr/bin/env python

import sys
import pika
import uuid
import json
import time
import itertools
from multiprocessing.dummy import Pool as ThreadPool, Manager as ThreadManager
import psycopg2
from psycopg2 import sql


import foursquare
import utils


RABBITMQ_HOST = "colossus07"
RABBITMQ_QUEUE = "rpc_study_queue"

DATA_PATH = "/home/ucfabb0/enigma/data/foursquare/dataset_TIST2015/"
FILTERED_POIS = DATA_PATH + "dataset_TIST2015_POIs_filtered.txt"


def print_progress(s):
    sys.stdout.write("\r\x1b[K" + s)
    sys.stdout.flush()


def monitor_map_progress(map_result, d, total, title="Progress: "):
    while True:
        if map_result.ready():
            break
        else:
            size = sum(1 for k in d.keys() if d[k] == 'done')
            s = title + "%.2f done" % (100 * size / total)
            # s += " [%s]" % (", ".join([str(k) for k in d.keys() if d[k] == 'running']))
            print_progress(s)
            time.sleep(0.5)


class PlaceWorkerRpcClient(object):
    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))

        self.channel = self.connection.channel()

        result = self.channel.queue_declare(exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(self.on_response, no_ack=True,
                                   queue=self.callback_queue)

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = body

    def call(self, s):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(exchange='',
                                   routing_key=RABBITMQ_QUEUE,
                                   properties=pika.BasicProperties(
                                         reply_to=self.callback_queue,
                                         correlation_id=self.corr_id,
                                         ),
                                   body=str(s))
        while self.response is None:
            self.connection.process_data_events()
        return json.loads(self.response.decode('utf-8'))


def process_venue(t):
    """ Process the venue from the tuple t: (venue_id, venue_data).
        Creating thread safe with the RabbitMQ server. """

    venue_id, d = t
    if d is not None:
        d[venue_id] = 'running'

    worker = PlaceWorkerRpcClient()
    _ = worker.call(venue_id)

    if d is not None:
        d[venue_id] = 'done'

    return venue_id


def process_venue_list(venue_id_list):
    pool = ThreadPool(5)
    m = ThreadManager()
    d = m.dict()

    for venue_id in venue_id_list:
        d[venue_id] = 'none'

    print("[.] Processing %s venues" % len(venue_id_list))
    result = pool.map_async(process_venue, zip(venue_id_list, itertools.repeat(d)))
    monitor_map_progress(result, d, len(venue_id_list))

    result.wait()
    _ = result.get()

    print("[x] Done with %s venues" % len(venue_id_list))


def get_venues_reviewed():
    connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("SELECT DISTINCT place_id FROM places;")
    cursor.execute(query_string)
    return [record['place_id'] for record in cursor]


def print_usage():
    print("Usage:   %s venue venue_id" % (sys.argv[0]))
    print("         %s venues-reviewed" % (sys.argv[0]))
    print("         %s all" % (sys.argv[0]))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print_usage()
        sys.exit(1)

    argument = sys.argv[1]
    if argument == "venue":
        if len(sys.argv) != 3:
            print("Usage:   %s venue venue_id" % (sys.argv[0]))
            sys.exit(1)

        venue_id = sys.argv[2]
        print("[.] Processing venue %s" % venue_id)
        result = process_venue((venue_id, None))
        print("[.] Done with venue %s" % result)
        sys.exit(1)

    elif argument == "venues-reviewed":
        venues_list = get_venues_reviewed()
        process_venue_list(venues_list)
        sys.exit(1)

    elif argument == "all":
        # get the venues that were already collected.
        venue_ids = set(foursquare.get_all_place_ids_from_place_personal_information_in_db())
        print("[x] Got %s venues already collected" % len(venue_ids))

        venues_list = []
        with open(FILTERED_POIS, 'r') as f:
            for line in f:
                fields = line.strip().split('\t')
                venue_id = fields[0]
                if venue_id in venue_ids:
                    continue

                venues_list.append(venue_id)

        process_venue_list(venues_list)
        sys.exit(1)

    else:
        print_usage()
        sys.exit(1)

