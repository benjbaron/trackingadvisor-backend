import os
import random
import time
import json
import requests
import math
import psycopg2
import psycopg2.extras
import itertools
from collections import OrderedDict
from multiprocessing.dummy import Pool as ThreadPool, Manager as ThreadManager
import utils

DB_HOSTNAME = "localhost"
if "DB_HOSTNAME" in os.environ:
    DB_HOSTNAME = os.environ.get("DB_HOSTNAME")


# Foursquare API
# API reference: https://developer.foursquare.com/start/search
BASE_URL = "https://api.foursquare.com/v2/"

TOKENS   = [ 'HHQYVTJRQD4MS3QANEXGBS2PYKWUJHV5URB3X4VXRCFKSJBL',
             'BYICTUH30Y45SZ0CFVWCDAHSCFODE5KGDALBQDJARBSRB4QO',
             'VYTYZPMIMDOOYNP12OWCGLC5Q4D4EHNEZ1EFL3VZOKXQSM1K']

# CLIENT_ID / CLIENT_SECRET
KEY_LIST = [ ('UXQJUKSEPFLXCMWAYG3LCUN4EVMIBRT4QBHMTRZWYNRTVCWH', 'R2LT0QC52L5J5VH3JPRT01QZLURXWIAU5DB4XFYOHK3ONBWA'),
             ('HD5ZYV1DJSQE2FXEX32F54205X43WQ3W2LTEVORFD413OCAL', '1JGVNUDPLFNTDMLYA0I4DMW0ERPVYAFUMJAULLUJVCKHLBKP'),
             ('3X13LKHOUSQBZEVOIKKCB1SZXOMM3CGDIVB2AOG5CSRGJSEZ', 'LCEAEEM5PDHXOIBAARA3O5T5NYT0D1NP1HU0KDJ3BGJIJWYC'),
             ('PJERQVMJ3DURUE5YKR50CSQGMYIPIBZQESKBK35SC1ZXQJ0R', 'XKGURJJDVQT3TSARQJDUR1BGZ1YIKR2K5Z4GGQOJ5RCAXTM3'),
             ('NYY01RBFH3PEC2XYSYWTXFWVH2DHYW2NGORESKYBUWR5COHZ', '1QZL5ZKF1KC1PLDGD41NS1YZCK1SRQPU2ERZEZCVIUHRVL0G'),
             ('0KW04LKJUIFPEYFZ011Z1L5UU5UXORKJKMVFJTKBH5JOPJEV', 'TA212WH5H5B2ARYTQARH00UGXBEVWMG5NZGPY5KPUFD2JHFH'),
             ('R0J2KFNC0CM3JQ4JMYPGJ4EOVI2BVYZFNDWHTZ3IC1SEC0V0', 'GE0VQDKUAF2UQELYZDZUPKVIZX1MXWRKWRMHU3T3WU5ZFCJ4'),
             ('OOABRTLTA4Y1AB1B3QE25PZSYQXA2QW44DBQ0EKHD0PWXAHP', 'V1GZ3HPDHFGP1LSI21KOGXTW2JV0HFJHCSBQLDERT03ODXWF'),
             ('TXRYPUX0100TCJG0R3ZVLNKA0YFHCVGJDCDRUMI4EY25TEU0', 'IPI0ESJWVZSBCJZINMVSLGUWPNAZEE2F2DCSOPEYD2KCQ5PA'),
             ('30LJR5G3E5LHC3NFQXLBCUH3N2VAHOJXWWGOHJSOMKZIRPLN', 'LY0DHCDNK3VG02CRYVWAAKNZ4TBGZWE23WPOHUIP0LT1P2MH'),
             ('WG1X3D40V4LABK45YMWLFKG3Y1GNNXAGUEFRVJXNBAQWESK0', 'PUTCDRHPF3VBCUQA2YLXMCJRFVB5UKELBWGDMXIF3LYLZFNM'),
             ('BFRJ3J4EFLHHQBB0R5ATGOMKZ2JZO2YGUHUUCAZNPQNMJK54', 'DC2MMNMC0T5OULPUHKCBYOXWKCADT1S3GXPKBFO4QOWWLL3E'),
             ('HD5ZYV1DJSQE2FXEX32F54205X43WQ3W2LTEVORFD413OCAL', '1JGVNUDPLFNTDMLYA0I4DMW0ERPVYAFUMJAULLUJVCKHLBKP'),
             ('MYH5IQJT4SRKSQHQ53UWHV0EYKKI1K1LOKYHLCKAT31E3RVQ', 'YP2SZZD3AAIZHHAHKWGKSINDTS5YXQTHJJ11KZ0NXSCDBJL5'),
             ('EGX2LKRNC5J0QRRXKJ33REBPBTCVQL4M1GTQDLL40VISKU00', 'CSEKWLCAJIJMX2L53MBS4P4W32KZNG1A0SNC1EBH3NDUHTSP'),
             ('Q4EYGAQKVBB3PE55L2KPDBOZVVCIYRPJ4BZXELADAQZW45LG', 'X5JF2RIKSVGYAFPI4IWWPDZ4YNKH540TFEOBK35HYAV2U3NA'),
             ('IQMGFYI41KXAO2VSDLXN3Y0UKQ3XBFIEE0PII2K4XE3S1DV3', 'WQFPPA2NUH5O0TXGM3J1OG4WCOOQDA2UHP2P2V234TOODKUZ')]

NB_MAX_REQ = (len(TOKENS) + len(KEY_LIST)) * 2 # max number of requests that we allow the session to do in a row


def get_client():
    if random.random() < 0.2:
        # Authenticated user access (with token)
        idx = random.randint(0, len(TOKENS)-1)
        return "oauth_token=%s" % (TOKENS[idx])
    else:
        # userless access
        idx = random.randint(0, len(KEY_LIST)-1)
        return "client_id=%s&client_secret=%s" % (KEY_LIST[idx][0], KEY_LIST[idx][1])


def send_request(base, params={}):
    """ Forms the request to send to the API and returns the data if no errors occured """
    nb_req = 0
    while nb_req < NB_MAX_REQ:
        full_url = base + "?" + "&".join(["%s=%s" % (k,v.replace(' ','+')) for (k,v) in params.items()])
        if len(params) > 0:
            full_url += "&" + get_client()
        else:
            full_url += get_client()
        full_url += "&v=20150906&m=foursquare&locale=en"

        try:
            data = requests.get(full_url).json()  # json.load(urllib2.urlopen(full_url))
        except:
            print("Failed getting the response")
            nb_req += 1
            time.sleep(min(1,nb_req/10))
            continue

        if 'error' in data or 'response' not in data:
            nb_req += 1
            time.sleep(min(1, nb_req/10))
            continue
        else:
            return data
    return None


def get_places(location, distance=50, limit=5):
    # check whether the location is within a search area
    if not is_location_in_db(location, distance):
        print("location {} not in database".format(location))
        get_all_places(location)

    places = get_places_from_db(location, distance, limit)
    return places


def get_venue(t):
    venue_id, d = t
    d[venue_id] = 'running'
    if is_place_in_db(venue_id):
        return venue_id

    get_complete_venue(venue_id)
    d[venue_id] = 'done'
    return venue_id


def get_autocomplete(location, query, distance=250, limit=8):
    url = BASE_URL
    params = {
        "ll": "%s,%s" % (location['lat'], location['lon']),
        "limit": str(limit),
        "radius": str(distance)
    }
    venue_key_string = ""

    if query == "":
        url += "venues/search"
        params['intent'] = 'checkin'
        venue_key_string = "venues"
    else:
        url += "venues/suggestcompletion"
        params['query'] = query
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

            results.append({
                "name": venue['name'],
                "placeid": venue['id'],
                "category": category,
                "city": venue['location']['city'],
                "distance": venue['location']['distance'],
                "origin": "foursquare-api"
            })
    return results


def get_autocomplete_from_db(location, query, distance=250, limit=8):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query_string = ""
    data = None
    if query == "":
        query_string = """
        WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
        )
        SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, 
               ST_Distance(ST_TRANSFORM(v3.geom, 3857), p.coords) as distance, v2.categories, 
               (0.25*v3.nb_checkins / max_checkins + 1.5 / SQRT(ST_Distance(ST_TRANSFORM(v3.geom, 3857), p.coords))) as weight
        FROM (
            SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories,
                   MAX(v1.nb_checkins) as max_checkins
            FROM (
                SELECT v.venue_id, v.nb_checkins, unnest(categories) as category_id
                FROM venues v, place p
                WHERE v.city <> '' 
                  AND ST_DWITHIN(ST_TRANSFORM(v.geom, 3857), p.coords, %s)
            ) v1 JOIN categories c ON c.category_id = v1.category_id
            GROUP BY venue_id
        ) v2 JOIN venues v3  ON v2.venue_id = v3.venue_id, place p
        ORDER BY weight DESC, distance ASC
        LIMIT %s;"""
        data = (location['lon'], location['lat'], distance, limit)
    else:
        query_string = """
        WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords, %s as name
        )
        SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, word_similarity(v3.name, p.name) as sml, 
               ST_Distance(ST_TRANSFORM(v3.geom, 3857), p.coords) as distance, v2.categories
        FROM (
            SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories
            FROM (
                SELECT v.venue_id, unnest(categories) as category_id
                FROM venues v, place p
                WHERE v.city <> '' AND p.name <%% v.name 
                  AND ST_DWITHIN(ST_TRANSFORM(v.geom, 3857), p.coords, %s)
            ) v1 JOIN categories c ON c.category_id = v1.category_id
            GROUP BY venue_id
        ) v2 JOIN venues v3  ON v2.venue_id = v3.venue_id, place p
        ORDER BY sml DESC, v3.nb_checkins DESC
        LIMIT %s;"""
        data = (location['lon'], location['lat'], query, distance, limit)

    cursor.execute(query_string, data)
    results = []
    for record in cursor:
        category = record['categories'][0] if len(record['categories']) > 0 else ""
        results.append({
            "name": record['name'],
            "placeid": record['venue_id'],
            "category": category,
            "city": record['city'],
            "distance": record['distance'],
            "origin": "foursquare-cache"
        })

    return results


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
    save_search_area_to_db(location, boundary, distance)


def is_place_in_db(venue_id):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query_string = """SELECT COUNT(*) FROM venues WHERE venue_id = %s;"""
    cursor.execute(query_string, (venue_id,))
    count = cursor.fetchone()[0]
    return count > 0


def get_places_from_db(location, distance=50, limit=5):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
    SELECT v.venue_id, v.name, v.nb_checkins, v.latitude, v.longitude, v.rating, v.price_tier, v.nb_likes, v.nb_tips,
    v.city, v.address, v.phrases, t.chains, t.categories, t.distance
    FROM (
        SELECT v1.venue_id, v1.distance, array_agg(DISTINCT c.name ORDER BY c.name) as categories, 
               array_agg(DISTINCT ch.name ORDER BY ch.name) as chains
        FROM (
            SELECT venue_id,
            ST_Distance(ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s,%s),4326),3857), ST_TRANSFORM(geom, 3857)) AS distance,
            unnest(v1.categories) as category_id,
            unnest(v1.chains) as chain_id
            FROM venues v1
            WHERE ST_DWithin(ST_TRANSFORM(geom, 3857), 
                             ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s), 4326), 3857), 
                             %s)
        ) v1 JOIN categories c ON c.category_id = v1.category_id
             LEFT OUTER JOIN chains ch ON ch.chain_id = v1.chain_id
        GROUP BY v1.venue_id, v1.distance
    ) t JOIN venues v  ON v.venue_id = t.venue_id
    ORDER BY v.nb_checkins DESC
    LIMIT %s;"""

    data = (location['lon'], location['lat'], location['lon'], location['lat'], distance, limit)

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
               "rating": rec['rating'],
               "likes": rec['nb_likes'],
               "price": rec['price_tier'],
               "location": {
                  "lon": rec['longitude'],
                  "lat": rec['latitude'],
                  "city": rec['city'],
                  "address": rec['address']
               },
               "tips": rec['nb_tips']
        }
        places.append(loc)

    return places


def is_location_in_db(location, distance=50):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor()

    query_string = """
    SELECT ST_Within(point, bigunion)
    FROM (
        SELECT ST_UNION(ST_Transform(area, 3857)) AS bigunion,
        ST_Buffer(ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857), %s) AS point
        FROM search_areas
    ) AS foo;"""
    data = (location['lon'], location['lat'], distance)

    cursor.execute(query_string, data)
    return cursor.fetchone()[0]


def save_search_area_to_db(location, boundary, distance):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor()

    location_point = "POINT({} {})".format(location['lon'], location['lat'])
    area_polygon = utils.boundary_to_wkt_polygon(boundary)
    query_string = """INSERT INTO search_areas 
    (date_added, longitude, latitude, distance, area, location)
    VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326))"""
    data = (int(time.time()), location['lon'], location['lat'], distance, area_polygon, location_point)

    cursor.execute(query_string, data)
    connection.commit()


def get_complete_venue(venue_id):
    url = BASE_URL + "venues/%s" % venue_id
    data = send_request(url)
    venue = data['response']['venue']

    save_venue_to_db(venue)

    nb_tips = venue['stats'].get('tipCount', 0)
    if nb_tips > 0:
        tips = get_all_tips_per_venue(venue_id)
        for tip in tips:
            save_tip_to_db(tip, venue_id)

    return venue


def save_venue_to_db(venue):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor()

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
    geom = "POINT({} {})".format(longitude, latitude)

    # Save the different chains
    if len(chains) > 0:
        for chain in venue['venueChains']:
            save_chain_to_db(chain)

    query_string = """INSERT INTO venues 
    (venue_id, categories, chains, phrases, postcode, address, city, rating, nb_checkins, nb_tips, 
    nb_likes, longitude, latitude, country, country_code, name, instagram, twitter, phone, facebook, 
    facebook_id, facebook_name, price_tier, price_message, price_currency, date_added, parent_id,  geom) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            ST_GeomFromText(%s, 4326))
    ON CONFLICT DO NOTHING;"""
    data = (venue_id, categories, chains, phrases, postcode, address, city, rating, nb_checkins, nb_tips,
            nb_likes, longitude, latitude, country, country_code, name, instagram, twitter, phone, facebook,
            facebook_id, facebook_name, price_tier, price_message, price_currency, date_added, parent_id, geom)

    cursor.execute(query_string, data)
    connection.commit()

    # get the parent
    if parent_id != "" and not is_place_in_db(parent_id):
        get_complete_venue(parent_id)


def save_chain_to_db(chain):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor()

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


def save_categories_to_db():
    def save_categories(categories, parent_id):
        connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
        cursor = connection.cursor()

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
    save_categories(categories, "")


def get_all_tips_per_venue(venue_id):
    url = BASE_URL + "venues/%s/tips" % venue_id
    offset = 0
    limit  = 500
    params = {
        "intent": "browse",
        "limit": str(limit),
        "offset": str(offset)
    }

    data = send_request(url, params)
    # get the total number of tips
    nrof_tips = data['response']['tips']['count']
    tips = data['response']['tips']['items']

    for i in range(1, int(math.ceil(nrof_tips / limit))):
        params['offset'] = str(limit * i)
        data = send_request(url, params)
        tips += data['response']['tips']['items']

    return tips


def save_tip_to_db(tip, venue_id):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor()

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


def save_user_to_db(user):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor()

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


def dump_categories_list():
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

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


def get_category(category_id):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
    SELECT c1.name as name, c2.name as parent_name
    FROM categories c1
    JOIN categories c2 ON c1.parent_id = c2.category_id
    WHERE c1.category_id = %s;"""

    cursor.execute(query_string, (category_id,))
    return cursor.fetchone()['name']


def get_category_of_venue(venue_id):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
    SELECT c.name as name
    FROM(
        SELECT unnest(v.categories) as category_id
        FROM venues v
        WHERE v.venue_id = %s
    ) v1
    LEFT OUTER JOIN categories c ON c.category_id = v1.category_id;"""

    cursor.execute(query_string, (venue_id,))
    return [c['name'] for c in cursor]


def get_personal_information_of_venue(venue_id):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

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


def autocomplete_location(location, query, distance=800, limit=10):
    if not is_location_in_db(location):
        print("location {} not in database".format(location))
        return get_autocomplete(location, query, distance, limit)
    else:
        print("location {} in database".format(location))
        return get_autocomplete_from_db(location, query, distance, limit)


if __name__ == '__main__':
    # initialize the database
    save_categories_to_db()
    print("Done")
