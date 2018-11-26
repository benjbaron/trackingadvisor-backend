import sys
import pika
import logging
import requests
import time
from langdetect import detect
from multiprocessing import Pool
import itertools
import datetime
import calendar
from collections import Counter
import mmap
import tqdm
import random
import json

import utils
import foursquare
from keys import WSID_OAUTH_TOKENS

NB_MAX_REQ = 10
BASE_URL = "https://api.foursquare.com/v2/"

RABBITMQ_HOST = "colossus07"
RABBITMQ_QUEUE = "rpc_fsq_tips_queue"


def send_request(base, params={}):
    """ Forms the request to send to the API and returns the data if no errors occurred """
    nb_req = 0
    while nb_req < NB_MAX_REQ:
        full_url = base + "?" + "&".join(["%s=%s" % (k, v.replace(' ', '+')) for (k, v) in params.items()])
        full_url += "&v=20181019&m=foursquare&locale=en"
        try:
            data = requests.get(full_url).json()  # json.load(urllib2.urlopen(full_url))
        except Exception as e:
            print("Failed getting the response")
            print(e.__doc__)
            nb_req += 1
            time.sleep(min(1, nb_req / 10))
            continue

        if 'error' in data or 'response' not in data or not data['response']:
            nb_req += 1
            time.sleep(min(1, nb_req / 10))
            continue
        else:
            if 'meta' in data and 'errorType' in data['meta'] and data['meta']['errorType'] == 'quota_exceeded':
                print("error: quota_exceeded")
            return data
    return None


def get_all_tips_per_venue(venue_id, params={}):
    url = BASE_URL + "venues/%s/tips" % venue_id
    offset = 0
    limit = 150
    params["intent"] = "browse"
    params["limit"] = str(limit)
    params["offset"] = str(offset)
    params["sort"] = "popular"

    data = send_request(url, params)
    nb_req = 0
    while nb_req < NB_MAX_REQ and data and 'tips' not in data['response']:
        data = send_request(url)
        nb_req += 1

    if nb_req == NB_MAX_REQ:
        print('Could not retrieve tips from venue {}'.format(venue_id))
        return {}

    if data is None or 'response' not in data:
        print("error with venue %s" % (venue_id))
        return []

    tips = data['response']['tips']['items']
    nb_tips = len(tips)

    i = 1
    while nb_tips == limit:
        params['offset'] = str(limit * i)
        data = send_request(url, params)
        try:
            tips += data['response']['tips']['items']
        except KeyError:
            print("KeyError with 'tips': {}".format(data))
        else:
            nb_tips = len(data['response']['tips']['items'])
            i += 1

    return tips


def save_tip_to_db(t):
    tip, venue_id = t
    connection, cursor = utils.connect_to_db("foursquare")

    tip_id = tip['id']
    created_at = tip['createdAt']
    text = tip['text']
    tip_type = tip['type']
    nb_likes = tip.get('likes', {}).get('count', 0)
    justification = tip.get('justification', {}).get('message', '')
    justification_type = tip.get('justification', {}).get('justificationType', '')
    user_id = tip.get('user', {}).get('id', '')
    try:
        lang = detect(tip['text'])
    except:
        lang = ''
    nb_agree = tip.get('agreeCount', 0)
    entities = [e['text'] for e in tip['entities'] if 'text' in e] if 'entities' in tip else []

    query_string = """INSERT INTO tips 
        (venue_id, tip_id, user_id, created_at, text, nb_likes, type, justification_type, justification, lang, nb_agree, entities) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tip_id) DO UPDATE SET 
          nb_likes=EXCLUDED.nb_likes, 
          justification=EXCLUDED.justification,
          justification_type=EXCLUDED.justification_type,
          lang=EXCLUDED.lang,
          nb_agree=EXCLUDED.nb_agree,
          entities=EXCLUDED.entities;"""
    data = (
    venue_id, tip_id, user_id, created_at, text, nb_likes, tip_type, justification_type, justification, lang, nb_agree,
    entities)

    cursor.execute(query_string, data)
    connection.commit()

    if 'user' in tip:
        save_user_to_db(tip['user'])


def save_user_to_db(user):
    connection, cursor = utils.connect_to_db("foursquare")

    user_id = user['id']
    gender = user.get('gender', '')
    firstname = user.get('firstName', '')
    lastname = user.get('lastName', '')
    photo_url = user.get('photo', {}).get('prefix', '') + '150x150' + user.get('photo', {}).get('suffix', '')
    canonical_path = user.get('canonicalPath', '')

    query_string = """INSERT INTO users
        (user_id, gender, firstname, lastname, photo_url, canonical_path)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET canonical_path=EXCLUDED.canonical_path, gender=EXCLUDED.gender;"""
    data = (user_id, gender, firstname, lastname, photo_url, canonical_path)

    cursor.execute(query_string, data)
    connection.commit()


def get_wsid_oauth_params():
    idx = random.randint(0, len(WSID_OAUTH_TOKENS)-1)
    wsid, oauth = WSID_OAUTH_TOKENS[idx]
    return wsid, oauth


def save_tips(venue_id, pool=None):
    if pool is None:
        pool = Pool(10)

    wsid, oauth = get_wsid_oauth_params()
    params = {
        "wsid": wsid,
        "oauth_token": oauth
    }

    tips = get_all_tips_per_venue(venue_id, params)

    # print("[.] Got %s tips" % (len(tips)))
    pool.map(save_tip_to_db, zip(tips, itertools.repeat(venue_id)))
    return tips


# Helper functions.
def get_num_lines(file_path):
    fp = open(file_path, "r+")
    buf = mmap.mmap(fp.fileno(), 0)
    lines = 0
    while buf.readline():
        lines += 1
    return lines


def date_to_timestamp(s):
    """ Convert "str" to millisecond timestamp. """
    d = s[:-10] + s[-4:]
    return 1000 * int(calendar.timegm(datetime.datetime.strptime(d, "%a %b %d %H:%M:%S %Y").utctimetuple()))


def on_request(ch, method, properties, body):
    global pool

    start_ts = int(time.time())
    place_id = body.decode("utf-8")

    logging.info(" [.] Getting tips for %s" % place_id)
    response = save_tips(place_id, pool)
    logging.info(" [.] Got %s tips for %s" % place_id)

    ch.basic_publish(exchange='',
                     routing_key=properties.reply_to,
                     properties=pika.BasicProperties(correlation_id=properties.correlation_id),
                     body=json.dumps(response))

    end_ts = int(time.time())

    logging.info(" [x] Done in %s seconds" % (end_ts - start_ts,))
    ch.basic_ack(delivery_tag=method.delivery_tag)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Missing an argument...")
        sys.exit(0)

    argument = sys.argv[1]

    if argument == 'venue':
        if len(sys.argv) != 3:
            print("Missing venue identifier")
            sys.exit(0)
        venue_id = sys.argv[2]
        tips = save_tips(venue_id)
        print("Got %s tips for venue %s" % (len(tips), venue_id))

    elif argument == 'all':
        FQS_CHECKINS_PATH = "/home/ucfabb0/enigma/data/foursquare/dataset_TIST2015/"
        FQS_CHECKINS_FILTERED = FQS_CHECKINS_PATH + "dataset_TIST2015_Checkins_filtered.txt"
        FQS_CHECKINS_FILTERED_POIS = FQS_CHECKINS_PATH + "dataset_TIST2015_POIs_filtered.txt"
        FSQ_OUTPUT_FILE = "foursquare_places_tips_retrieved.txt"

        checkins_venues = {}

        with open(FQS_CHECKINS_FILTERED, 'r') as f:
            count = 0
            for line in tqdm.tqdm(f, total=get_num_lines(FQS_CHECKINS_FILTERED)):
                count += 1
                fields = line.strip().split('\t')
                user_id = fields[0]
                venue_id = fields[1]
                date_string = fields[2]
                utc_offset = int(fields[3])
                try:
                    d = date_to_timestamp(date_string)
                    d += utc_offset
                except ValueError as e:
                    print("error with line: %s" % line.rstrip())
                    continue

                if venue_id not in checkins_venues:
                    checkins_venues[venue_id] = []
                checkins_venues[venue_id].append((user_id, d))

        print("[.] Processed %s checkins" % count)
        print("[.] Got %s checkins at venues from the Foursquare checkins dataset." % (len(checkins_venues)))

        done_venue_ids = set()
        with open(FSQ_OUTPUT_FILE, 'r') as f:
            for line in f:
                fields = line.strip().split(',')
                venue_id = fields[0]
                done_venue_ids.add(venue_id)

        with open(FSQ_OUTPUT_FILE, 'a') as f:
            counter = Counter([venue_id for venue_id, checkins in checkins_venues.items() for c in checkins])
            count = 0
            tot_count = len(counter)
            pool = Pool(10)
            for venue_id, n in counter.most_common():
                if venue_id in done_venue_ids:
                    count += 1
                    continue

                venue = foursquare.get_place(venue_id)
                if venue is None:
                    print("error: no venue (%s)" % venue_id)
                    continue

                tips = save_tips(venue_id, pool)
                nb_tips = len(tips)
                utils.print_progress("[%s / %s] %s Getting tips for venue %s (%s) with %s tips..." % (count, tot_count, venue['emoji'], venue['name'], venue_id, nb_tips))
                f.write("%s,%s,%s,%s\n" % (venue_id, venue['name'], n, nb_tips))
                count += 1

    elif argument == 'listen':
        # Set up the logging
        logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                            level=logging.INFO)

        # Set up the RabbitMQ channel
        # Tutorial: https://www.rabbitmq.com/tutorials/tutorial-six-python.html
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        channel.queue_declare(queue=RABBITMQ_QUEUE)

        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(on_request,
                              queue=RABBITMQ_QUEUE)

        ts = int(time.time())
        pool = Pool(10)
        logging.info(' [x] Waiting for RPC requests...')

        channel.start_consuming()

    else:
        print("unknown argument - %s" % argument)
        sys.exit(0)


