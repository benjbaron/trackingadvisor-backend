import os
import sys
import random
import time
import json
import requests
import math
import itertools
import re
import sys
import pprint
from collections import OrderedDict
from multiprocessing.dummy import Pool as ThreadPool, Manager as ThreadManager
import psycopg2.extras

from keys import *

import utils

ERROR_TYPE_GEOCODE_TOO_BIG = "geocode_too_big"

# Foursquare API
# API reference: https://developer.foursquare.com/start/search
BASE_URL = "https://api.foursquare.com/v2/"

NB_MAX_REQ = (len(TOKENS) + len(KEY_LIST)) * 2  # max number of requests that we allow the session to do in a row
QUOTA_EXCEEDED = set()


def get_client():
    # user-less access
    key_list = [KEY_LIST[i] for i in range(len(KEY_LIST)) if i not in QUOTA_EXCEEDED]
    idx = random.randint(0, len(key_list)-1)
    return idx, "client_id=%s&client_secret=%s" % (KEY_LIST[idx][0], KEY_LIST[idx][1])


def construct_url(base, params={}):
    full_url = base + "?" + "&".join(["%s=%s" % (k, v.replace(' ', '+')) for (k, v) in params.items()])
    idx, client = get_client()
    if len(params) > 0:
        full_url += "&" + client
    else:
        full_url += client
    full_url += "&v=20150906&m=foursquare&locale=en"
    return full_url


def send_request(base, params={}):
    """ Forms the request to send to the API and returns the data if no errors occurred """
    nb_req = 0
    while nb_req < NB_MAX_REQ:
        full_url = base + "?" + "&".join(["%s=%s" % (k, v.replace(' ', '+')) for (k, v) in params.items()])
        idx, client = get_client()
        if len(params) > 0:
            full_url += "&" + client
        else:
            full_url += client
        full_url += "&v=20150906&m=foursquare&locale=en"
        try:
            data = requests.get(full_url).json()  # json.load(urllib2.urlopen(full_url))
        except Exception as e:
            print("Failed getting the response")
            print(e.__doc__)
            nb_req += 1
            time.sleep(min(1, nb_req/10))
            continue

        if 'error' in data or 'response' not in data or not data['response']:
            nb_req += 1
            time.sleep(min(1, nb_req/10))
            continue
        else:
            if 'meta' in data and 'errorType' in data['meta'] and data['meta']['errorType'] == 'quota_exceeded':
                QUOTA_EXCEEDED.add(idx)
            return data
    return None


def test_api_keys(base, params={}):
    base_url = base + "?" + "&".join(["%s=%s" % (k, v.replace(' ', '+')) for (k, v) in params.items()])
    count = 0
    for client_id, secret_id in KEY_LIST:
        full_url = base_url + "&" + "client_id=%s&client_secret=%s" % (client_id, secret_id)
        full_url += "&v=20150906&m=foursquare&locale=en"
        try:
            data = requests.get(full_url).json()
        except:
            print("Exception: Failed getting the response\n..Client ID: {}\n..Secret ID: {}".format(client_id, secret_id))
            continue

        if 'error' in data or 'response' not in data or not data['response']:
            print("Invalid key pair\n..Client ID: {}\n..Secret ID: {}".format(client_id, secret_id))
            if 'meta' in data and 'errorType' in data['meta']:
                print("..Error: {} ({})".format(data['meta']['errorType'], data['meta']['code']))
            continue

        print("Done for key #{}".format(count))
        count += 1


def sort_place_score(places):
    res = []
    max_nb_checkins = 0
    min_distance = 100
    for place in places:
        if place['checkins'] > max_nb_checkins:
            max_nb_checkins = place['checkins']
        if place['distance'] < min_distance:
            min_distance = place['distance']

    for place in places:
        checkin_ratio = 0 if max_nb_checkins == 0 else place['checkins'] / max_nb_checkins
        distance_ratio = 1 if place['distance'] == 0 else place['distance']
        score = 0.1 * checkin_ratio + 1.5 / math.sqrt(distance_ratio)
        place['score'] = score
        res.append((score, place))

    return [e[1] for e in sorted(res, key=lambda x: x[0], reverse=True)]


def get_place(venue_id, connection=None, cursor=None):

    if not is_place_in_db(venue_id, connection=connection, cursor=cursor):
        print("venue not in DB (%s), fetching..." % venue_id)
        get_complete_venue(venue_id)

    print("venue in DB (%s)" % venue_id)
    return get_complete_venue_from_db(venue_id, connection=connection, cursor=cursor)


def get_places(location, distance=50, limit=5, connection=None, cursor=None):
    # check whether the location is within a search area
    if not is_location_in_db(location, distance):
        get_all_places(location)

    places = get_places_from_db(location, distance, limit, connection=connection, cursor=cursor)
    return places


def get_venue(t):
    """ Get the venue from the tuple t: (venue_id, venue_data).
        Creating thread-safe psycopg2 connection and cursor. """
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    venue_id, d = t
    d[venue_id] = 'running'
    if is_place_in_db(venue_id, connection=connection, cursor=cursor):
        d[venue_id] = 'done'
        return venue_id

    get_complete_venue(venue_id, connection=connection, cursor=cursor)
    d[venue_id] = 'done'
    return venue_id


def get_autocomplete(location, query, distance=250, limit=8):
    url = BASE_URL
    params = {
        "ll": "%s,%s" % (location['lat'], location['lon']),
        "limit": str(limit)
    }

    if query == "":
        url += "venues/search"
        params['intent'] = 'checkin'
        params['radius'] = str(distance)
        venue_key_string = "venues"
    else:
        url += "venues/suggestcompletion"
        params['query'] = query
        params['radius'] = str(10*distance)
        venue_key_string = "minivenues"

    data = send_request(url, params)
    results = []
    if 'response' in data and venue_key_string in data['response']:
        for venue in data['response'][venue_key_string]:
            if 'city' not in venue['location']:
                continue
            if 'distance' not in venue['location'] or venue['location']['distance'] >= distance:
                continue

            category = venue['categories'][0]['name'] if len(venue['categories']) > 0 else ""
            categories = {'categories': [cat['id'] for cat in venue['categories']]}
            emoji, icon = get_icon_for_venue(venue['id'], categories)
            results.append({
                "name": venue['name'],
                "venueid": venue['id'],
                "placeid": "",
                "category": category,
                "city": venue['location'].get('city', ""),
                "address": venue['location'].get('address', ""),
                "checkins": 0,
                "score": venue['location']['distance'],
                "latitude": venue['location']['lat'],
                "longitude": venue['location']['lng'],
                "distance": venue['location']['distance'],
                "origin": "foursquare-api",
                "icon": icon,
                "emoji": emoji
            })
    return results


def get_autocomplete_from_db(location, query, distance=250, limit=8, cursor=None):
    if cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    
    query_string = ""
    data = None

    if query == "":
        print("[Autocomplete] (%s, %s)" % (location['lon'], location['lat']))
        query_string = """
        WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
        )
        SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, v3.latitude, v3.longitude,
               ST_Distance(ST_TRANSFORM(v3.geom, 3857), p.coords) as distance, v2.categories, v3.icon, v3.emoji
        FROM (
            SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories
            FROM (
                SELECT v.venue_id, v.nb_checkins, unnest(categories) as category_id
                FROM venues v, place p
                WHERE ST_DWITHIN(ST_TRANSFORM(v.geom, 3857), p.coords, %s)
            ) v1 JOIN categories c ON c.category_id = v1.category_id
            GROUP BY venue_id
        ) v2 JOIN venues v3  ON v2.venue_id = v3.venue_id, place p
        ORDER BY nb_checkins DESC, distance ASC
        LIMIT %s;"""
        data = (location['lon'], location['lat'], distance, limit)
    else:
        print("[Autocomplete] (%s, %s) %s" % (location['lon'], location['lat'], query))
        query_string = """
        WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords, %s as name
        )
        SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, v3.latitude, v3.longitude, 
               word_similarity(v3.name, p.name) as sml, v3.icon, v3.emoji,
               ST_Distance(ST_TRANSFORM(v3.geom, 3857), p.coords) as distance, v2.categories
        FROM (
            SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories
            FROM (
                SELECT v.venue_id, unnest(categories) as category_id
                FROM venues v, place p
                WHERE p.name <%% v.name 
                  AND ST_DWITHIN(ST_TRANSFORM(v.geom, 3857), p.coords, %s)
            ) v1 JOIN categories c ON c.category_id = v1.category_id
            GROUP BY venue_id
        ) v2 JOIN venues v3  ON v2.venue_id = v3.venue_id, place p
        ORDER BY sml DESC, distance ASC, v3.nb_checkins DESC
        LIMIT %s;"""
        data = (location['lon'], location['lat'], query, 10*distance, limit)

    start_time = time.time()
    cursor.execute(query_string, data)
    end_time = time.time()
    print("elapsed (2): %.5f" % (end_time - start_time))

    start_time = time.time()
    results = []
    for record in cursor:
        category = record['categories'][0] if len(record['categories']) > 0 else ""
        results.append({
            "name": record['name'],
            "venueid": record['venue_id'],
            "placeid": "",
            "category": category,
            "city": record['city'],
            "address": record['address'],
            "latitude": record['latitude'],
            "longitude": record['longitude'],
            "checkins": record['nb_checkins'],
            "distance": record['distance'],
            "origin": "foursquare-cache",
            "icon": record['icon'],
            "emoji": record['emoji']
        })
    end_time = time.time()
    print("elapsed (3): %.5f" % (end_time - start_time))

    start_time = time.time()
    sorted_places = sort_place_score(results)
    end_time = time.time()
    print("elapsed (4): %.5f" % (end_time - start_time))

    return sorted_places


def get_place_with_name(location, query, distance=200, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH place AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords, %s as query
    )
    SELECT name, venue_id, parent_id, longitude, latitude, chains, description, phrases, nb_checkins, rating, price_tier,
           word_similarity(name, p.query) as sml, 
           ST_Distance(p.coords, ST_TRANSFORM(geom, 3857)) as distance
    FROM venues, place p
    WHERE p.query <%% name 
          AND ST_DWITHIN(ST_TRANSFORM(geom, 3857), p.coords, %s)
    ORDER BY sml DESC, distance DESC
    LIMIT 1;"""
    data = (location['lon'], location['lat'], query, distance)

    cursor.execute(query_string, data)
    rec = cursor.fetchone()

    loc = {"name": rec['name'],
           "id": rec['venue_id'],
           "parent_id": rec['parent_id'],
           "chains": rec['chains'],
           "description": rec['description'],
           "phrases": rec['phrases'],
           "distance": rec['distance'],
           "sml": rec['sml'],
           "location": {
               "lon": rec['longitude'],
               "lat": rec['latitude']
             }
           }

    return loc


def get_place_with_id(venue_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT name, venue_id, parent_id, longitude, latitude, chains, description, phrases, nb_checkins, rating, price_tier
    FROM venues
    WHERE venue_id = %s
    LIMIT 1;"""
    data = (venue_id,)

    cursor.execute(query_string, data)
    rec = cursor.fetchone()

    loc = {"name": rec['name'],
           "id": rec['venue_id'],
           "parent_id": rec['parent_id'],
           "chains": rec['chains'],
           "description": rec['description'],
           "phrases": rec['phrases'],
           "location": {
               "lon": rec['longitude'],
               "lat": rec['latitude']
             }
           }

    return loc


def get_all_places_from_db(location, distance=150, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
        WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
        )        
        SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, v3.latitude, v3.longitude, 
               ST_Distance(ST_TRANSFORM(v3.geom, 3857), p.coords) as distance, v2.categories
        FROM (
            SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories
            FROM (
                SELECT v.venue_id, unnest(categories) as category_id
                FROM venues v, place p
                WHERE ST_DWITHIN(ST_TRANSFORM(v.geom, 3857), p.coords, %s)
            ) v1 JOIN categories c ON c.category_id = v1.category_id
            GROUP BY venue_id
        ) v2 JOIN venues v3  ON v2.venue_id = v3.venue_id, place p   
        ORDER BY distance ASC;"""
    data = (location['lon'], location['lat'], user_id, distance)

    cursor.execute(query_string, data)
    places = [dict(record) for record in cursor]
    return places


def get_places_within_bounding_box(neLat, neLng, swLat, swLng, limit=25, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT name, latitude, longitude, address, city
    FROM   venues
    WHERE  geom 
        @
        ST_MakeEnvelope (
            %s, %s, -- bounding 
            %s, %s, -- box limits
            4326)
    ORDER BY nb_checkins DESC
    LIMIT %s;"""
    data = (swLng, swLat, neLng, neLat, limit)

    cursor.execute(query_string, data)
    places = [dict(record) for record in cursor]
    return places


def get_all_places(location, distance=125):
    boundary = utils.bounding_box(location["lat"], location["lon"], distance / 1000.0)

    def query_cell(cell):
        params = {
            "sw": "%s,%s" % (cell["southwest"]["lat"], cell["southwest"]["lng"]),
            "ne": "%s,%s" % (cell["northeast"]["lat"], cell["northeast"]["lng"]),
            "intent": "browse",
            "limit": "50"
        }
        url = BASE_URL + "venues/search"
        data = send_request(url, params)
        venues = data['response']['venues']
        if len(venues) == 50:
            # Divide the search area in four subcells
            res = []
            cells = utils.divide_cells(cell)
            for c in cells:
                res += query_cell(c)
            return res
        else:
            return venues

    places = query_cell(boundary)
    print("Retrieved {} places".format(len(places)))

    pool = ThreadPool(10)
    m = ThreadManager()
    d = m.dict()
    venues_list = []
    for place in places:
        venue_id = place['id']
        venues_list.append(venue_id)
        d[venue_id] = 'none'

    result = pool.map_async(get_venue, zip(venues_list, itertools.repeat(d)))
    utils.monitor_map_progress(result, d, len(venues_list))

    result.wait()
    _ = result.get()

    print('')

    # Save the search area in the database
    print("Saving search area to DB")
    save_search_area_to_db(location, boundary, distance)


def is_place_in_db(venue_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """SELECT COUNT(1) FROM venues WHERE venue_id = %s;"""
    cursor.execute(query_string, (venue_id,))
    count = cursor.fetchone()[0]
    return count > 0


def get_places_from_db(location, distance=50, limit=5, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH place AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
    )
    SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, v3.latitude, v3.longitude, v2.categories, 
           v3.rating,v3.nb_likes, v3.price_tier, v3.nb_tips, v3.emoji, v3.icon, v3.categories as category_ids,
           ST_Distance(ST_TRANSFORM(v3.geom, 3857), p.coords) as distance
    FROM (
        SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories,
               MAX(v1.nb_checkins) as max_checkins
        FROM (
            SELECT v.venue_id, v.nb_checkins, unnest(categories) as category_id
            FROM venues v, place p
            WHERE ST_DWITHIN(ST_TRANSFORM(v.geom, 3857), p.coords, %s)
        ) v1 JOIN categories c ON c.category_id = v1.category_id
        GROUP BY venue_id
        LIMIT %s
    ) v2 JOIN venues v3  ON v2.venue_id = v3.venue_id, place p
    ORDER BY nb_checkins DESC, distance ASC;"""

    data = (location['lon'], location['lat'], distance, limit)

    cursor.execute(query_string, data)
    records = cursor.fetchall()

    places = []
    for rec in records:
        loc = {"name": rec['name'],
               "color": "#f94877",
               "category": rec['categories'],
               "id": rec['venue_id'],
               "distance": rec["distance"],
               "checkins": rec['nb_checkins'],
               "emoji": rec['emoji'],
               "icon": rec['icon'],
               "rating": rec['rating'],
               "likes": rec['nb_likes'],
               "price": rec['price_tier'],
               "category_id": rec['category_ids'],
               "location": {
                  "lon": rec['longitude'],
                  "lat": rec['latitude'],
                  "city": rec['city'],
                  "address": rec['address']
               },
               "tips": rec['nb_tips']
        }
        places.append(loc)

    return sort_place_score(places)


def is_location_in_db(location, distance=50, cursor=None):
    if cursor is None:
        connection, cursor = utils.connect_to_db("foursquare")

    query_string = """
    WITH point AS (
      SELECT ST_Buffer(ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857), %s) as buffer
    )
    SELECT id
    FROM search_areas, point
    WHERE ST_Within(point.buffer, ST_Transform(area, 3857));"""
    data = (location['lon'], location['lat'], distance)

    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return res[0] > 0 if res else False


def save_search_area_to_db(location, boundary, distance, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare")

    location_point = "POINT({} {})".format(location['lon'], location['lat'])
    area_polygon = utils.boundary_to_wkt_polygon(boundary)
    query_string = """INSERT INTO search_areas 
    (date_added, longitude, latitude, distance, area, location)
    VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326))"""
    data = (utils.current_timestamp(), location['lon'], location['lat'], distance, area_polygon, location_point)

    cursor.execute(query_string, data)
    connection.commit()


def get_complete_venue(venue_id, connection=None, cursor=None):
    url = BASE_URL + "venues/%s" % venue_id
    data = send_request(url)
    nb_req = 0
    while nb_req < NB_MAX_REQ and data and 'venue' not in data['response']:
        data = send_request(url)
        nb_req += 1

    if nb_req == NB_MAX_REQ:
        print('Could not retrieve venue {}'.format(venue_id))
        return {}

    if data is None or 'response' not in data or 'venue' not in data['response']:
        print("no response from the venue")
        return None

    venue = data['response']['venue']
    if ('venueRatingBlacklisted' in venue and venue['venueRatingBlacklisted']) or ('deleted' in venue and venue['deleted']):
        print("venue is deleted or blacklisted - skip venue")
        return {}

    save_venue_to_db(venue, redirect_venue_id=venue_id, connection=connection, cursor=cursor)

    nb_tips = venue['stats'].get('tipCount', 0)
    if nb_tips > 0:
        tips = get_all_tips_per_venue(venue_id)
        for tip in tips:
            save_tip_to_db(tip, venue_id, connection=connection, cursor=cursor)

    return venue


def get_complete_venue_from_db(venue_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
        SELECT v.venue_id, v.name, v.nb_checkins, v.latitude, v.longitude, v.rating, v.price_tier, v.nb_likes, v.nb_tips,
        v.city, v.address, v.phrases, t1.categories, t2.chains, v.emoji, v.icon
        FROM (
            SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories
            FROM (
                SELECT venue_id,
                unnest(coalesce(nullif(v1.categories,'{}'), array[null::text])) as category_id
                FROM venues v1
                WHERE venue_id = %s
            ) v1 JOIN categories c ON c.category_id = v1.category_id
            GROUP BY v1.venue_id
        ) t1, 
        (
            SELECT v2.venue_id, array_agg(DISTINCT ch.name ORDER BY ch.name) as chains
            FROM (
                SELECT venue_id,
                unnest(coalesce(nullif(v2.chains,'{}'),array[null::text])) as chain_id
                FROM venues v2
                WHERE venue_id = %s
            ) v2 LEFT OUTER JOIN chains ch ON ch.chain_id = v2.chain_id
            GROUP BY v2.venue_id
        ) t2
        JOIN venues v ON v.venue_id = t2.venue_id
        ORDER BY v.nb_checkins DESC
        LIMIT 1;"""

    data = (venue_id, venue_id,)

    cursor.execute(query_string, data)
    rec = cursor.fetchone()

    if rec is None or 'name' not in rec:
        return None

    place = {
        "name": rec['name'],
        "color": "#f94877",
        "category": rec['categories'],
        "id": rec['venue_id'],
        "checkins": rec['nb_checkins'],
        "rating": rec['rating'],
        "nb_likes": rec['nb_likes'],
        "nb_tips": rec['nb_tips'],
        "price": rec['price_tier'],
        "emoji": rec['emoji'],
        "icon": rec['icon'],
        "location": {
            "lon": rec['longitude'],
            "lat": rec['latitude'],
            "city": rec['city'],
            "address": rec['address']
        },
        "tips": get_all_tips_per_venue_from_db(venue_id)
    }

    return place


def save_venue_to_db(venue, redirect_venue_id=None, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare")

    venue_id = venue['id']
    name = venue['name']
    longitude = venue['location']['lng']
    latitude = venue['location']['lat']
    postcode = venue['location'].get('postalCode', "")
    country = venue['location'].get('country', "")
    country_code = venue['location'].get('cc', "")
    address = venue['location'].get('address', "")
    city = venue['location'].get('city', "")
    rating = venue.get('rating', 0.0)
    nb_checkins = venue['stats'].get('checkinsCount', 0)
    nb_tips = venue['stats'].get('tipCount', 0)
    nb_likes = venue.get('likes', {}).get('count', 0)
    categories = [cat['id'] for cat in venue['categories']]
    chains = [chain['id'] for chain in venue.get('venueChains', [])]
    instagram = venue['contact'].get('instagram', "")
    twitter = venue['contact'].get('twitter', "")
    phone = venue['contact'].get('phone', "")
    phrases = [phrase['phrase'] for phrase in venue.get('phrases', [])]
    facebook = venue['contact'].get('facebookUsername', "")
    facebook_id = venue['contact'].get('facebook', "")
    facebook_name = venue['contact'].get('facebookName', "")
    price_tier = venue.get('price', {}).get('tier', 0)
    price_message = venue.get('price', {}).get('message', "")
    price_currency = venue.get('price', {}).get('currency', "")
    date_added = int(time.time())
    parent_id = venue.get('parent', {}).get('id', "")
    description = venue.get('description', "")
    geom = "POINT({} {})".format(longitude, latitude)

    print("venue: %s (%s / %s)" % (name, venue_id, redirect_venue_id))

    c = {'categories': categories}
    emoji, icon = get_icon_for_venue(venue_id, c)

    # Save the different chains
    if len(chains) > 0:
        for chain in venue['venueChains']:
            save_chain_to_db(chain)

    query_string = """INSERT INTO venues 
    (venue_id, categories, chains, phrases, postcode, address, city, rating, nb_checkins, nb_tips, redirect_venue_id,
    nb_likes, longitude, latitude, country, country_code, name, instagram, twitter, phone, facebook, icon, emoji,
    facebook_id, facebook_name, price_tier, price_message, price_currency, date_added, parent_id, description, geom) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
    ON CONFLICT DO NOTHING;"""
    data = (venue_id, categories, chains, phrases, postcode, address, city, rating, nb_checkins, nb_tips, None,
            nb_likes, longitude, latitude, country, country_code, name, instagram, twitter, phone, facebook, icon, emoji,
            facebook_id, facebook_name, price_tier, price_message, price_currency, date_added, parent_id, description, geom)
    cursor.execute(query_string, data)

    if redirect_venue_id != venue_id:
        # Save a new venue with the same attributes except for the venue_id
        data = (redirect_venue_id, categories, chains, phrases, postcode, address, city, rating, nb_checkins, nb_tips, venue_id,
                nb_likes, longitude, latitude, country, country_code, name, instagram, twitter, phone, facebook, icon,
                emoji, facebook_id, facebook_name, price_tier, price_message, price_currency, date_added, parent_id,
                description, geom)
        cursor.execute(query_string, data)

    connection.commit()

    # get the parent
    if parent_id != "" and not is_place_in_db(parent_id, connection=connection, cursor=cursor):
        get_complete_venue(parent_id)


def save_chain_to_db(chain, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare")

    chain_id = chain['id']
    name = chain.get('bestName', {}).get('name', '')
    logo_url = chain.get('logo', {}).get('prefix', '') + '150x150' + chain.get('logo', {}).get('suffix', '')

    query_string = """INSERT INTO chains 
            (chain_id, name, logo_url) 
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING;"""
    data = (chain_id, name, logo_url)

    cursor.execute(query_string, data)
    connection.commit()


def get_categories():
    url = BASE_URL + "venues/categories"
    data = send_request(url)
    return data['response']['categories']


def save_categories_to_db(connection=None, cursor=None):
    def save_categories(categories, parent_id, connection=None, cursor=None):
        if connection is None and cursor is None:
            connection, cursor = utils.connect_to_db("foursquare")

        for category in categories:
            query_string = """
            INSERT INTO categories
            (category_id, parent_id, name, shortname, pluralname, icon, personal_information)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING;"""

            category_id = category['id']
            name = category['name']
            pluralname = category['pluralName']
            shortname = category['shortName']
            icon = category.get('icon', {}).get('prefix', '') + '150x150' + category.get('icon', {}).get('suffix', '')

            data = (category_id, parent_id, name, shortname, pluralname, icon, "{}")
            cursor.execute(query_string, data)

            child_categories = category['categories']
            if child_categories:
                save_categories(child_categories, category_id)

        connection.commit()

    categories = get_categories()
    save_categories(categories, "", connection=connection, cursor=cursor)


def get_all_tips_per_venue(venue_id):
    url = BASE_URL + "venues/%s/tips" % venue_id
    offset = 0
    limit = 150
    params = {
        "intent": "browse",
        "limit": str(limit),
        "offset": str(offset)
    }

    data = send_request(url, params)
    nb_req = 0
    while nb_req < NB_MAX_REQ and data and 'tips' not in data['response']:
        data = send_request(url)
        nb_req += 1

    if nb_req == NB_MAX_REQ:
        print('Could not retrieve tips from venue {}'.format(venue_id))
        return {}

    print(data)

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


def get_all_tips_per_venue_from_db(venue_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
            SELECT t.tip_id, t.created_at, t.text, t.nb_likes, t.justification, t.justification_type, t.user_id, 
                   u.firstname, u.lastname, u.gender, t.lang
            FROM tips t JOIN users u ON u.user_id = t.user_id      
            WHERE t.venue_id = %s  
            ORDER BY t.created_at DESC;"""

    data = (venue_id,)

    cursor.execute(query_string, data)
    records = cursor.fetchall()

    return [dict(rec) for rec in records]


def save_tip_to_db(tip, venue_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare")

    tip_id = tip['id']
    created_at = tip['createdAt']
    text = tip['text']
    tip_type = tip['type']
    nb_likes = tip.get('likes', {}).get('count', 0)
    justification = tip.get('justification', {}).get('message', '')
    justification_type = tip.get('justification', {}).get('justificationType', '')
    user_id = tip.get('user', {}).get('id', '')

    query_string = """INSERT INTO tips 
        (venue_id, tip_id, user_id, created_at, text, nb_likes, type, justification_type, justification) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING;"""
    data = (venue_id, tip_id, user_id, created_at, text, nb_likes, tip_type, justification_type, justification)

    cursor.execute(query_string, data)
    connection.commit()

    if 'user' in tip:
        save_user_to_db(tip['user'])


def save_user_to_db(user, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare")

    user_id = user['id']
    gender = user.get('gender', '')
    firstname = user.get('firstName', '')
    lastname = user.get('lastName', '')
    photo_url = user.get('photo', {}).get('prefix', '') + '150x150' + user.get('photo', {}).get('suffix', '')

    query_string = """INSERT INTO users
        (user_id, gender, firstname, lastname, photo_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING"""
    data = (user_id, gender, firstname, lastname, photo_url)

    cursor.execute(query_string, data)
    connection.commit()


def get_all_checkins_per_venue(venue_id):
    url = BASE_URL + "venues/%s/herenow" % venue_id
    data = send_request(url)
    return data['response']


def dump_categories_list(connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT c1.name, c1.category_id, c1.parent_id, c2.name as parent_name
    FROM categories c1
    JOIN categories c2 ON c1.parent_id = c2.category_id;"""

    cursor.execute(query_string)
    records = cursor.fetchall()
    with open("categories.csv", 'w') as f:
        for rec in records:
            f.write("%s;%s;%s\n" % (rec['name'], rec['parent_name'], rec['category_id']))
    print("Done")


def get_category(category_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT c1.name as name, c2.name as parent_name
    FROM categories c1
    JOIN categories c2 ON c1.parent_id = c2.category_id
    WHERE c1.category_id = %s;"""

    cursor.execute(query_string, (category_id,))
    return cursor.fetchone()['name']


def get_category_of_venue(venue_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT c.name as name, c.category_id as id
    FROM(
        SELECT unnest(v.categories) as category_id
        FROM venues v
        WHERE v.venue_id = %s
    ) v1
    LEFT OUTER JOIN categories c ON c.category_id = v1.category_id;"""

    cursor.execute(query_string, (venue_id,))
    return [dict(c) for c in cursor]


def get_foursquare_categories(connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT category_id, parent_id, name
    FROM categories;"""
    cursor.execute(query_string)
    return [dict(res) for res in cursor]


def get_all_categories(connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH RECURSIVE t(category_id, parents, parents_name) AS (
        SELECT category_id, ARRAY[]::text[], ARRAY[]::text[] FROM categories WHERE parent_id = ''
      UNION ALL
        SELECT c.category_id, c.parent_id || t.parents, c1.name || t.parents_name
        FROM categories c
        JOIN t ON parent_id = t.category_id
        JOIN categories c1 ON c1.category_id = c.parent_id
    )
    SELECT c.name, c.icon, t.category_id, t.parents, t.parents_name 
    FROM t INNER JOIN categories c ON c.category_id = t.category_id;"""

    cursor.execute(query_string)
    return [dict(res) for res in cursor]


def get_all_categories_with_personal_information(connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH RECURSIVE t(category_id, parents, parents_name) AS (
        SELECT category_id, ARRAY[]::text[], ARRAY[]::text[] FROM categories WHERE parent_id = ''
      UNION ALL
        SELECT c.category_id, c.parent_id || t.parents, c1.name || t.parents_name
        FROM categories c
        JOIN t ON parent_id = t.category_id
        JOIN categories c1 ON c1.category_id = c.parent_id
    )
    SELECT c2.name, c2.icon, c2.category_id, m2.pis, t.parents, t.parents_name
    FROM (
        SELECT c1.category_id, json_agg(jsonb_build_object('name', m.name, 'category', m.category_id, 'pi_id', m.pi_id)) as pis
        FROM (
            SELECT c.category_id, unnest(c.pi_ids) as piid
            FROM categories c
        ) pi JOIN personal_information m ON uuid(pi.piid) = m.pi_id
             FULL OUTER JOIN categories c1 ON pi.category_id = c1.category_id
        GROUP BY c1.category_id
    ) m2 FULL OUTER JOIN categories c2 ON c2.category_id = m2.category_id
         FULL OUTER JOIN t ON t.category_id = m2.category_id
    WHERE c2.category_id IS NOT NULL;"""
    cursor.execute(query_string)
    return [dict(res) for res in cursor]


def get_category_info_from_id(category_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH RECURSIVE t(category_id, parents, parents_name) AS (
        SELECT category_id, ARRAY[]::text[], ARRAY[]::text[] FROM categories WHERE parent_id = ''
      UNION ALL
        SELECT c.category_id, c.parent_id || t.parents, c1.name || t.parents_name
        FROM categories c
        JOIN t ON parent_id = t.category_id
        JOIN categories c1 ON c1.category_id = c.parent_id
    )
    SELECT c.name, c.icon, t.category_id, t.parents, t.parents_name 
    FROM t INNER JOIN categories c ON c.category_id = t.category_id
    WHERE t.category_id = %s;"""

    cursor.execute(query_string, (category_id,))
    res = cursor.fetchone()
    return dict(res) if res else {}


def get_all_personal_information(connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_sting = """
    SELECT pi_id, name, category_id, subcategory_icon, category_icon, subcategory_name
    FROM personal_information
    ORDER BY category_id, subcategory_name, name;"""

    cursor.execute(query_sting)
    res = []
    for e in cursor:
        d = dict(e)
        d['icon'] = d['subcategory_icon'] if d['subcategory_icon'] != '' else d['category_icon']
        res.append(d)

    return res


def get_places_from_users(connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
    SELECT name, type, category, venue_id, place_id
    FROM places;"""
    cursor.execute(query_string)
    return [dict(res) for res in cursor]


def get_category_ids_for_venue(venue_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT categories
    FROM venues
    WHERE venue_id = %s;"""
    data = (venue_id, )

    cursor.execute(query_string, data)
    cat_ids = [dict(record) for record in cursor]

    return cat_ids[0] if cat_ids else None


def get_personal_information_of_venue(venue_id, connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT unnest(c.personal_information) as personal_info
    FROM(
        SELECT unnest(v.categories) as category_id
        FROM venues v
        WHERE v.venue_id = %s
    ) v1
    LEFT OUTER JOIN categories c ON c.category_id = v1.category_id
    GROUP BY personal_info;"""

    cursor.execute(query_string, (venue_id,))
    personal_information = {}
    for c in cursor:
        info = c['personal_info']
        cat, keys = utils.decode_personal_information(info)
        if cat not in personal_information:
            personal_information[cat] = set()

        if keys:
            personal_information[cat].update(keys)

    return dict((cat, list(keys)) for cat, keys in personal_information.items())


def get_icon_for_venue(venue_id, categories=None, connection=None, cursor=None):
    emoji = '👣'
    icon = 'map-marker'

    if not categories:
        categories = get_category_ids_for_venue(venue_id, connection=connection, cursor=cursor)

    print(categories)

    if categories['categories']:
        categories_res = get_icons_from_category_ids(categories['categories'], connection=connection, cursor=cursor)
        print(categories_res)
        cat_ids = [c for c in categories_res if categories_res[c]['leaf']]
        cat_id = list(categories_res.keys())[0] if not cat_ids else cat_ids[-1]
        emoji = categories_res[cat_id]['emoji']
        icon = categories_res[cat_id]['icon']

    return emoji, icon


def get_icons_from_category_ids(category_ids, connection=None, cursor=None):
    if not category_ids:
        return OrderedDict()

    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT emoji, icon, category_id, leaf
    FROM categories
    WHERE category_id IN %s;"""
    cursor.execute(query_string, (tuple(category_ids),))
    return OrderedDict([(res['category_id'], dict(res)) for res in cursor])


def get_icon_from_category_ids(category_ids):
    filtered_category_ids = [c for c in category_ids if c in leaf_nodes]
    category_id = category_ids[0] if not filtered_category_ids else filtered_category_ids[0]

    fname = "supp/personal_information_foursquare.csv"
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(';')
        for line in f:
            d = dict(zip(header, line.rstrip().split(';')))
            cat_id = d['ID']
            if cat_id == category_id:
                return d['EMOJI'], d['ICON'], category_id

    return None


def autocomplete_location(location, query, distance=250, limit=10, connection=None, cursor=None):
    print("foursquare location: %s, query: %s, distance: %s, limit: %s" % (location, query, distance, limit))
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    start_time = time.time()
    in_db = is_location_in_db(location, cursor=cursor)
    end_time = time.time()
    print("elapsed (1): %.5f" % (end_time - start_time))

    if not in_db:
        print("autocomplete from API")
        return get_autocomplete(location, query, distance, limit)
    else:
        print("autocomplete from DB")
        return get_autocomplete_from_db(location, query, distance, limit, cursor=cursor)


def load_personal_information(connection=None, cursor=None):
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
    SELECT pi_id, name, category_id, subcategory_name, tags, category_icon
    FROM personal_information
    ORDER BY category_id ASC, name ASC;"""
    cursor.execute(query_string)
    return dict([(res['pi_id'], dict(res)) for res in cursor])


def save_place_personal_information_to_db(ppi, cursor=None):
    """ Save the place personal information (interests) ppi to the database """
    if not cursor:  # default behavior
        try_commit = True
        connection, cursor = utils.connect_to_db("foursquare")
    else:
        try_commit = False

    pi_id = ppi['pi_id']
    venue_id = ppi['place_id']
    feature_type = ppi['feature_type']
    avg = ppi['avg']
    phrase_modeler = ppi['phrase_modeler']
    model_type = ppi['model_type']
    score = ppi['score']
    rank = ppi['rank']
    tags = ppi['tags']

    query_string = """INSERT INTO place_personal_information
    (pi_id, venue_id, feature_type, avg, phrase_modeler, model_type, score, rank, tags)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING"""
    data = (pi_id, venue_id, feature_type, avg, phrase_modeler, model_type, score, rank, tags)

    cursor.execute(query_string, data)
    if try_commit:
        connection.commit()


def get_place_personal_information_from_db(venue_id, connection=None, cursor=None):
    """ Retrieves the place personal information (interests) ppi from the database """
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT ppi.pi_id, ppi.venue_id, ppi.feature_type, pi.name, pi.category_id, pi.category_icon, ppi.avg, 
           ppi.phrase_modeler, ppi.score, ppi.rank, ppi.tags, ppi.model_type
    FROM place_personal_information ppi
    JOIN personal_information pi on pi.pi_id = ppi.pi_id
    WHERE ppi.venue_id = %s
    ORDER BY ppi.rank;"""
    cursor.execute(query_string, (venue_id,))

    return [dict(res) for res in cursor]


def get_place_personal_information_aggregated_from_db(venue_id, connection=None, cursor=None):
    """ Retrieves the place personal information (interests) ppi from the database """
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT pi.pi_id, ppi.venue_id, pi.name, pi.category_id, pi.category_icon, 
    AVG(ppi.rank) as rank_avg, COUNT(ppi.id) as nb, AVG(ppi.score) as score_avg, 
    COUNT(ppi.id) * AVG(ppi.score) / (AVG(ppi.rank)+1) as res
    FROM place_personal_information ppi
    JOIN personal_information pi on pi.pi_id = ppi.pi_id
    WHERE venue_id = %s
    GROUP BY pi.pi_id, ppi.venue_id
    ORDER BY res DESC;"""
    cursor.execute(query_string, (venue_id,))

    return [dict(res) for res in cursor]


def has_place_personal_information_in_db(venue_id, connection=None, cursor=None):
    """ Returns true if there are personal information (interests) associated to the venue_id in the database. """

    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """SELECT COUNT(1) FROM place_personal_information WHERE venue_id = %s;"""
    cursor.execute(query_string, (venue_id,))
    count = cursor.fetchone()[0]
    return count > 0


def get_all_place_ids_from_place_personal_information_in_db(connection=None, cursor=None):
    """ Returns the list of the place ids of the places that are in the place_personal_information table. """
    if connection is None and cursor is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """SELECT venue_id FROM place_personal_information GROUP BY venue_id;"""
    cursor.execute(query_string)
    return [record['venue_id'] for record in cursor]


def get_all_places_within_location(location='', args='location'):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    def get_failed_urls():
        pattern = r"sw=([\+\-\d.]+),([\+\-\d.]+)\&ne=([\+\-\d.]+),([\+\-\d.]+)"
        cells = []
        with open('foursquare_failed.txt', 'r') as f:
            for line in f:
                m = re.search(pattern, line)
                cell = {
                    "northeast": {
                        "lat": float(m.group(3)),
                        "lng": float(m.group(4))
                    },
                    "southwest": {
                        "lat": float(m.group(1)),
                        "lng": float(m.group(2))
                    }
                }
                cells.append(cell)
        return cells

    def query_cell(cell):
        res = []
        if len(cell) == 0:
            return res

        params = {
            "sw": "%s,%s" % (cell["southwest"]["lat"], cell["southwest"]["lng"]),
            "ne": "%s,%s" % (cell["northeast"]["lat"], cell["northeast"]["lng"]),
            "intent": "browse",
            "limit": "50"
        }
        url = BASE_URL + "venues/search"
        data = send_request(url, params)

        if data['meta']['code'] == 400:
            # there was an error
            print("Error: {}".format(data['meta']['errorType']))
            if data['meta']['errorType'] == ERROR_TYPE_GEOCODE_TOO_BIG:
                # Divide the search area in four subcells
                cells = utils.divide_cells(cell)
                for c in cells:
                    res += query_cell(c)
                return res

        nb_req = 0
        while nb_req < 10 and 'venues' not in data['response']:
            data = send_request(url, params)
            nb_req += 1

        if nb_req == 10:
            print('Could not retrieve venues from cell {} / {}'.format(cell, nb_req))
            print(construct_url(url, params))
            return []

        venues = data['response']['venues']
        if len(venues) == 50:
            # Divide the search area in four subcells
            cells = utils.divide_cells(cell)
            for c in cells:
                res += query_cell(c)
            return res
        else:
            return venues

    def reduce_venues_to_process():
        venues = set()
        count = 0
        with open("foursquare_venues_dump.txt", 'r') as f:
            for line in f:
                venues.add(line.strip())
                count += 1

        with open("foursquare_venues.txt", 'w') as f:
            for venue_id in venues:
                f.write("%s\n" % (venue_id))

        print("Done reducing {} venues into {} unique venues".format(count, len(venues)))

    def retrieve_venues_from_cells():
        cells = get_failed_urls()
        count = 0
        count_venues = 0
        for cell in cells:
            places = query_cell(cell)
            print("Retrieved {} places for url #{}".format(len(places), count))
            count += 1

            with open('foursquare_venues_dump.txt', 'a') as f:
                for place in places:
                    venue_id = place['id']
                    f.write("%s\n" % (venue_id))
                    count_venues += 1
        print("Saved {} places in file foursquare_venues_dump.txt".format(count_venues))

    def get_venues_done():
        def worker_is_venue_in_db(t):
            venue_id, d = t
            d[venue_id] = 'running'
            res = is_place_in_db(venue_id, connection=connection, cursor=cursor)
            d[venue_id] = 'done'
            return venue_id, res

        m = ThreadManager()
        d = m.dict()
        venues = set()
        with open("foursquare_venues.txt", 'r') as f:
            for line in f:
                venue_id = line.strip()
                d[venue_id] = 'none'
                venues.add(venue_id)

        venues_list = list(venues)
        pool = ThreadPool(2)

        result = pool.map_async(worker_is_venue_in_db, zip(venues_list, itertools.repeat(d)))
        utils.monitor_map_progress(result, d, len(venues_list))

        result.wait()
        v = result.get()

        print('')

        with open("foursquare_venues_done.txt", 'w') as f:
            count = 0
            for venue_id, b in v:
                if b:
                    f.write("%s\n" % venue_id)
                    count += 1
        print("Saved {} venues already in the database".format(count))

    def retrieve_venues_from_file():
        venues_done = set()
        with open('foursquare_venues_done.txt', 'r') as f:
            for line in f:
                venue_id = line.strip()
                venues_done.add(venue_id)

        venues = []
        m = ThreadManager()
        d = m.dict()

        with open('foursquare_venues.txt', 'r') as f:
            for line in f:
                venue_id = line.strip()
                if venue_id not in venues_done:
                    venues.append(venue_id)
                    d[venue_id] = 'none'

        venues_list = venues
        pool = ThreadPool(20)

        result = pool.map_async(get_venue, zip(venues_list, itertools.repeat(d)))
        utils.monitor_map_progress(result, d, len(venues_list))

        result.wait()
        _ = result.get()

        print('')

    if args == 'venues-done':
        get_venues_done()
    elif args == 'venues-file':
        retrieve_venues_from_file()
    elif args == 'venues-cell':
        retrieve_venues_from_cells()
    elif args == 'save-search-area':
        # Save the search area in the database
        if location != '':
            print("Save the search area of {}".format(location))
            boundary, loc = utils.get_boundaries_from_location(location)
            print("Latitude: {}, longitude: {}".format(loc['lat'], loc['lon']))
            save_search_area_to_db(loc, boundary, 0)
    else:
        print("Error - unknown argument provided ({})".format(args))


if __name__ == '__main__':

    base = sys.argv[0]

    if len(sys.argv) == 1:
        print('Error - please provide an argument:')
        print('\t{} test-keys'.format(base))
        print('\t{} all "location"'.format(base))
        print('\t{} init-categories'.format(base))
        print('\t{} retrieve "venue_id'.format(base))
        print('\t{} in-db lon lat'.format(base))
        print('\t{} get-venues venues-done|venues-file|venues-cell|save-search-area'.format(base))
        sys.exit(0)

    argument = sys.argv[1]
    if argument == 'test-keys':
        # Test API keys
        venue_id = "4ac518cef964a52021a620e3"
        test_api_keys(BASE_URL + "venues/%s" % venue_id)
    elif argument == 'all':
        if len(sys.argv) == 3:
            location = sys.argv[2]
            # Load all the venues of a location (e.g., London, UK)
            get_all_places_within_location(location)
        else:
            print('Error - Please give us a location')
    elif argument == 'init-categories':
        # initialize the database with categories
        save_categories_to_db()
    elif argument == 'get-venues':
        if len(sys.argv) == 3:
            args = sys.argv[2]
            get_all_places_within_location(args=args)
        else:
            print('Error - Please give an additional argument (venues-done|venues-file|venues-cell|save-search-area)')
    elif argument == 'get-tips':
        if len(sys.argv) == 3:
            venue_id = sys.argv[2]
            venue_tips = get_all_tips_per_venue(venue_id)
            print(venue_tips)
        else:
            print('Error - Please give lon lat arguments')
    elif argument == 'find':
        if len(sys.argv) == 4:
            lon = sys.argv[2]
            lat = sys.argv[3]
            location = {"lon": lon, "lat": lat}
            fsq_places = get_places_from_db(location, 100, 5)
            print(fsq_places)
        else:
            print('Error - Please give lon lat arguments')
    elif argument == 'retrieve':
        if len(sys.argv) == 3:
            venue_id = sys.argv[2]
            get_complete_venue(venue_id)
        else:
            print('Error - Please give venue_id argument')
    elif argument == 'icon':
        if len(sys.argv) == 3:
            venue_id = sys.argv[2]
            print(get_icon_for_venue(venue_id))
        else:
            print('Error - Please give venue_id argument')
    elif argument == 'in-db':
        if len(sys.argv) == 4:
            lon = float(sys.argv[2])
            lat = float(sys.argv[3])
            location = {"lon": lon, "lat": lat}
            res = is_location_in_db(location)
            print("Location (%s, %s) in db: %s" % (lon, lat, res))
        else:
            print('Error - Please give lon lat arguments')
    elif argument == 'venue':
        if len(sys.argv) == 3:
            venue_id = sys.argv[2]
            place = get_place(venue_id)
            if 'tips' in place:
                del place['tips']
            pprint.pprint(place)
        else:
            print('Error - Please give venue_id argument')
    else:
        print('Error - unknown argument provided ({})'.format(argument))
        sys.exit(0)

    # boundary, loc = utils.get_boundaries_from_location("Great Britain")
    # print(utils.boundary_to_geojson_polygon(boundary))

    # place = get_place(venue_id)
    # print(place['nb_tips'], len(place['tips']))
    # print("Done")
