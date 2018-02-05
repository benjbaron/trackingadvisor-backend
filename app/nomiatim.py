import sys
import random
import time
import json
import requests
import psycopg2.extras

import utils

# Nominatim API
# API reference: https://wiki.openstreetmap.org/wiki/Nominatim#Reverse_Geocoding
BASE_URL = " http://nominatim.openstreetmap.org/"
NB_MAX_REQ = 3
KEY_LIST = []


def send_request(base, params):
    """ Forms the request to send to the API and returns the data if no errors occurred """
    nb_req = 0
    while nb_req < NB_MAX_REQ:
        full_url = base + "?" + "&".join(["%s=%s" % (k, str(v).replace(' ', '+')) for (k, v) in params.items()])
        if len(KEY_LIST) > 0:
            if len(params) > 0:
                full_url += "&" + get_key()
            else:
                full_url += get_key()

        request = requests.get(full_url).json()
        if not request:
            nb_req += 1
            time.sleep(min(1, nb_req / 10))
            continue

        return request


def get_viewbox(location, distance):
    boundary = utils.bounding_box(location["lat"], location["lon"], distance / 1000.0)
    return "{},{},{},{}".format(boundary['southwest']['lng'],
                                boundary['southwest']['lat'],
                                boundary['northeast']['lng'],
                                boundary['northeast']['lat'])


def get_place_with_name(location, query, distance=200):
    params = {
        "format": "jsonv2",
        "q": query,
        "viewbox": get_viewbox(location, distance),
        "bounded": 1,
        "extratags": 1,
        "namedetails": 1,
        "polygon_text": 1,
        "limit": 1
    }

    data = send_request(BASE_URL+"search", params)
    if data:
        return data[0]
    return None


def get_places(location, limit=10):
    params = {
        "format": "jsonv2",
        "lat": "%s" % location["lat"],
        "lon": "%s" % location["lon"],
        "extratags": 1,
        "namedetails": 1,
        "node_type": "R",
        "polygon_text": 1,
        "limit": limit
    }

    data = send_request(BASE_URL+"reverse", params)
    if data:
        return data[0]
    return None


def get_foursquare_venue_polygon(venue_id):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
        SELECT venue_id, name, longitude, latitude
        FROM venues
        WHERE venue_id = %s;"""
    cursor.execute(query_string, (venue_id,))
    rec = cursor.fetchone()
    if not rec:
        return

    venue = dict(rec)
    location = {"lon": venue['longitude'], "lat": venue['latitude']}
    venue_name = venue['name']

    # get the polygon from nominatim
    print("get polygon for place {} with location {}, {}".format(venue_name, venue['longitude'], venue['latitude']))
    res = get_place_with_name(location, venue_name)
    if not res:
        return

    print("Found polygon")

    query_string = """
    UPDATE venues 
    SET poly = ST_GeomFromText(%s, 4326) 
    WHERE venue_id = %s;"""
    data = (res['geotext'], venue_id)
    cursor.execute(query_string, data)

    connection.commit()


def update_all_foursquare_venues_with_polygon():
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
    SELECT venue_id, name, longitude, latitude
    FROM venues;"""
    cursor.execute(query_string)
    records = cursor.fetchall()
    venues = [dict(e) for e in records]

    for venue in venues:
        location = {"lon": venue['longitude'], "lat": venue['latitude']}
        res = get_place_with_name(location, venue['name'])

        if not res or 'geotext' not in res:
            continue

        query_string = """
            UPDATE venues 
            SET poly = ST_GeomFromText(%s, 4326) 
            WHERE venue_id = %s;"""
        data = (res['geotext'], venue['venue_id'])
        cursor.execute(query_string, data)

    connection.commit()


if __name__ == '__main__':
    base = sys.argv[0]

    if len(sys.argv) < 2:
        print("Error - please specify more arguments:")
        print("\t{} reverse lon lat".format(base))
        print("\t{} search lon lat location".format(base))
        sys.exit(0)

    arg = sys.argv[1]
    if arg == 'reverse':
        if len(sys.argv) != 4:
            print("Error - you need to specify a longitude and a latitude")
            sys.exit(0)

        lon = sys.argv[2]
        lat = sys.argv[3]
        location = {"lon": lon, "lat": lat}
        print(get_places(location))
    elif arg == 'search':
        if len(sys.argv) != 5:
            print("Error - you need to specify a longitude, a latitude, and a query")
            sys.exit(0)

        lon = sys.argv[2]
        lat = sys.argv[3]
        query = sys.argv[4]
        location = {"lon": lon, "lat": lat}
        print(get_place_with_name(location, query))
    elif arg == 'venue':
        if len(sys.argv) != 3:
            print("Error - you need to specify a foursquare venue id")
            sys.exit(0)

        venue_id = sys.argv[2]
        print(get_foursquare_venue_polygon(venue_id))
    else:
        print("Error - specify an argument search | reverse")
        sys.exit(0)
