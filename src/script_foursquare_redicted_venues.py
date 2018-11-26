#!/usr/bin/env python -W ignore::DeprecationWarning

import sys
import time
import mmap
import tqdm
import psycopg2
from psycopg2 import sql

import utils

FQS_CHECKINS_PATH = "/home/ucfabb0/enigma/data/foursquare/dataset_TIST2015/"
FQS_CHECKINS_FILTERED_POIS = FQS_CHECKINS_PATH + "dataset_TIST2015_POIs_filtered.txt"
FQS_CHECKINS_FILTERED = FQS_CHECKINS_PATH + "dataset_TIST2015_Checkins_filtered.txt"
FSQ_CHECKINS_FILTERED_POIS_REDIRECTED = FQS_CHECKINS_PATH + "dataset_TIST2015_POIs_filtered_redirected.txt"
FQS_CHECKINS_FILTERED_REDIRECTED = FQS_CHECKINS_PATH + "dataset_TIST2015_Checkins_filtered_redirected.txt"


REMOVE_VENUES = {
    '4e4e0ebd7d8bd425e47c386b',
    '4eb55eeae30006eb12161d81',
    '4eb82358be7bfc284b7111cd',
    '4ee3751af790897ecf6c005d',
    '4f2f0f24e4b0599150c213a5',
    '4f2f3f06e4b05a84d9cd5a19',
    '4f4221ebe4b0f96037b484d5',
    '4ffabfd5d86ca0c93937dc76',
    '503e9ed5e4b0167c10ad9183',
    '508f8d0ae4b063c6400e611f',
    '50939e28e4b0578aada38edd',
    '5093b2ade4b03898aef50986',
    '514c58bcf2e744feeaebb02a'
}


# Helper functions.
def get_num_lines(file_path):
    fp = open(file_path, "r+")
    buf = mmap.mmap(fp.fileno(), 0)
    lines = 0
    while buf.readline():
        lines += 1
    return lines


redirected_venues = dict()
nb_attempts = 10


def redirect_all_foursquare_venues():
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    with open(FSQ_CHECKINS_FILTERED_POIS_REDIRECTED, 'w') as f_out:
        with open(FQS_CHECKINS_FILTERED_POIS, 'r') as f:
            count = 0
            count_redirected = 0
            for line in tqdm.tqdm(f, total=get_num_lines(FQS_CHECKINS_FILTERED_POIS)):
                fields = line.strip().split('\t')
                venue_id = fields[0]
                if venue_id in REMOVE_VENUES:
                    continue

                redirected_venue_id, name, emoji = get_foursquare_redirected_venue(venue_id, connection=connection, cursor=cursor)
                fields.append(name)
                fields.append(emoji)
                if redirected_venue_id is not None:
                    redirected_venues[venue_id] = redirected_venue_id
                    fields[0] = redirected_venue_id
                    count_redirected += 1

                try:
                    f_out.write("\t".join(fields)+"\n")
                except:
                    print(venue_id)
                    # sys.exit(0)
                count += 1

    print("[.] Redirected %s venues out of %s from the Foursquare checkins dataset." % (count_redirected, count))


def redirect_all_foursquare_checkins():
    with open(FQS_CHECKINS_FILTERED_REDIRECTED, 'w') as f_out:
        with open(FQS_CHECKINS_FILTERED, 'r') as f:
            count = 0
            count_redirected = 0
            for line in tqdm.tqdm(f, total=get_num_lines(FQS_CHECKINS_FILTERED)):
                fields = line.strip().split('\t')
                venue_id = fields[1]
                if venue_id in REMOVE_VENUES:
                    continue

                if venue_id in redirected_venues:
                    fields[1] = redirected_venues[venue_id]
                    count_redirected += 1

                f_out.write("\t".join(fields)+"\n")
                count += 1


def get_foursquare_redirected_venue(venue_id, connection=None, cursor=None):
    global nb_attempts
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query = sql.SQL("""SELECT name, emoji, redirect_venue_id
            FROM venues
            WHERE venue_id = %s;""")
    cursor.execute(query, (venue_id,))
    try:
        res = cursor.fetchone()
        redirected_venue_id = res['redirect_venue_id']
        name = res['name']
        emoji = res['emoji']
        nb_attempts = 10
        return redirected_venue_id, name, emoji
    except:
        print("Retry")
        time.sleep(1)
        if nb_attempts >= 0:
            nb_attempts -= 1
            return get_foursquare_redirected_venue(venue_id, connection=connection, cursor=cursor)
        else:
            print("give up - venue %s" % venue_id)
            return None


if __name__ == '__main__':
    redirect_all_foursquare_venues()
    redirect_all_foursquare_checkins()

