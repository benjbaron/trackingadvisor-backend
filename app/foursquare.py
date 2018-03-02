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
from collections import OrderedDict
from multiprocessing.dummy import Pool as ThreadPool, Manager as ThreadManager
import psycopg2.extras

import utils

ERROR_TYPE_GEOCODE_TOO_BIG = "geocode_too_big"


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
             # ('NYY01RBFH3PEC2XYSYWTXFWVH2DHYW2NGORESKYBUWR5COHZ', '1QZL5ZKF1KC1PLDGD41NS1YZCK1SRQPU2ERZEZCVIUHRVL0G'),
             # ('0KW04LKJUIFPEYFZ011Z1L5UU5UXORKJKMVFJTKBH5JOPJEV', 'TA212WH5H5B2ARYTQARH00UGXBEVWMG5NZGPY5KPUFD2JHFH'),
             # ('R0J2KFNC0CM3JQ4JMYPGJ4EOVI2BVYZFNDWHTZ3IC1SEC0V0', 'GE0VQDKUAF2UQELYZDZUPKVIZX1MXWRKWRMHU3T3WU5ZFCJ4'),
             # ('OOABRTLTA4Y1AB1B3QE25PZSYQXA2QW44DBQ0EKHD0PWXAHP', 'V1GZ3HPDHFGP1LSI21KOGXTW2JV0HFJHCSBQLDERT03ODXWF'),
             ('TXRYPUX0100TCJG0R3ZVLNKA0YFHCVGJDCDRUMI4EY25TEU0', 'IPI0ESJWVZSBCJZINMVSLGUWPNAZEE2F2DCSOPEYD2KCQ5PA'),
             ('30LJR5G3E5LHC3NFQXLBCUH3N2VAHOJXWWGOHJSOMKZIRPLN', 'LY0DHCDNK3VG02CRYVWAAKNZ4TBGZWE23WPOHUIP0LT1P2MH'),
             ('WG1X3D40V4LABK45YMWLFKG3Y1GNNXAGUEFRVJXNBAQWESK0', 'PUTCDRHPF3VBCUQA2YLXMCJRFVB5UKELBWGDMXIF3LYLZFNM'),
             ('BFRJ3J4EFLHHQBB0R5ATGOMKZ2JZO2YGUHUUCAZNPQNMJK54', 'DC2MMNMC0T5OULPUHKCBYOXWKCADT1S3GXPKBFO4QOWWLL3E'),
             ('HD5ZYV1DJSQE2FXEX32F54205X43WQ3W2LTEVORFD413OCAL', '1JGVNUDPLFNTDMLYA0I4DMW0ERPVYAFUMJAULLUJVCKHLBKP'),
             ('MYH5IQJT4SRKSQHQ53UWHV0EYKKI1K1LOKYHLCKAT31E3RVQ', 'YP2SZZD3AAIZHHAHKWGKSINDTS5YXQTHJJ11KZ0NXSCDBJL5'),
             ('EGX2LKRNC5J0QRRXKJ33REBPBTCVQL4M1GTQDLL40VISKU00', 'CSEKWLCAJIJMX2L53MBS4P4W32KZNG1A0SNC1EBH3NDUHTSP'),
             ('Q4EYGAQKVBB3PE55L2KPDBOZVVCIYRPJ4BZXELADAQZW45LG', 'X5JF2RIKSVGYAFPI4IWWPDZ4YNKH540TFEOBK35HYAV2U3NA'),
             ('IQMGFYI41KXAO2VSDLXN3Y0UKQ3XBFIEE0PII2K4XE3S1DV3', 'WQFPPA2NUH5O0TXGM3J1OG4WCOOQDA2UHP2P2V234TOODKUZ'),
             ('4F0VKGAT4TU3PBD2HAUD0LSOJIWSXVAEMCT5PWGYPIVMMWAJ', 'AILRF3MQMNUZ3RAPBXBOCPZMW4XJJKQJLXIKBE1IPQHRZROJ'),
             ('OO5NWCVYRSZVNDXUDUDSJVWRPNXPEOEJRUGOJZGVEHQMTISJ', 'ZCFXECDNZJZPEFN3FSBCJKJCCJGPVWBSCRUTZL41F3NIWRLE'),
             ('1HFQTJEFGHY4FTMRIV0QKW3SGKYBYUYKBQTIHOMDHU3JFSGV', '5X3UDJO32XXATVZCISWXJ1R24VTDSY4W0O1PITSUP4VASP4O'),
             ('3X13LKHOUSQBZEVOIKKCB1SZXOMM3CGDIVB2AOG5CSRGJSEZ', 'LCEAEEM5PDHXOIBAARA3O5T5NYT0D1NP1HU0KDJ3BGJIJWYC'),
             ('KTXQOGJTKKG3NIDHXY5VMM2JM3T5QYS15XR0JVJPH0P0SQWU', '4AJ0T1OCN100CFDRCFOZZ2EV4TMSDDT0G5DRV4EFSUOQ4S1O'),
             ('WLJ4BLHFK5VYWRC0SRJSA3EAH5SFCIJRFID00A4H0AKEFKYZ', '2YPJE2PTCMR2MYXODUPB1SNJDTZAYVGP2DINHM1XCVDCPUEQ'),
             ('OOABRTLTA4Y1AB1B3QE25PZSYQXA2QW44DBQ0EKHD0PWXAHP', 'V1GZ3HPDHFGP1LSI21KOGXTW2JV0HFJHCSBQLDERT03ODXWF'),
             ('FSHPY2OMORSUOX1UPMF01QO5ADO0SZ1X53SF5VILHAY4YSMS', 'YOTIUZLLEFQ3JDM0X3FA1PQYHOZIBRMKJBB4DPZ41WPCGB4A'),
             ('ZOPC5XRDHB24TFTQUX5ZKHDTQB0SAQSEDEVKZ1GQ0UR2E3WX', 'EFNCN1WFPNB41YSWPSFZM43XMTJI2WPAQAUBLOW1F0E0LO4U'),
             ('30LJR5G3E5LHC3NFQXLBCUH3N2VAHOJXWWGOHJSOMKZIRPLN', 'LY0DHCDNK3VG02CRYVWAAKNZ4TBGZWE23WPOHUIP0LT1P2MH'),
             ('WG1X3D40V4LABK45YMWLFKG3Y1GNNXAGUEFRVJXNBAQWESK0', 'PUTCDRHPF3VBCUQA2YLXMCJRFVB5UKELBWGDMXIF3LYLZFNM'),
             ('5GYQRKZOWQSU1OYGELF3TE24RU4FGW1CSMHLCNOAD4UD3XIT', '32EDDW2J3W3EY4DVW4SAM22YDPLX1CUU2XE2VDVBCIAJOYGW'),
             ('IQMGFYI41KXAO2VSDLXN3Y0UKQ3XBFIEE0PII2K4XE3S1DV3', 'WQFPPA2NUH5O0TXGM3J1OG4WCOOQDA2UHP2P2V234TOODKUZ'),
             ('FHQ0N04L0YB2QPOV3H4LSV0HLYRICAQWZNGODU1QH1B2VA2G', 'XHGKDM1NFWBIQC1LKM0CFEJ5XL133H15FI2USAG2ZZ222B5N'),
             ('P3JSQUIXKFXFUWZGAHVYG0NHSYXQMJAYZQ5J3G3BLI34LOZO', 'XYPS1GKXNAOGJV0KMH41TQAGAXENDU4VGS22OYAOIGP3V2SR'),
             ('QTQYTWUWKGBI05BJKEYDHYLZWAJP3AUJ1UUUIBVTQMNFP3SO', '2LMVHJSHMDMXQCYIRUV4PLBVKSZALWEC4O4GDJGYRERZBCDD'),
             ('5XOWXECUBZAYTVY1EPA30CGWABN3FJY2XYSFIYK5FJ4WJNYS', '01T2ZQJVU5IYEXK4CF2A5LUFN1K5BEKLPDW3GCITXS4AUNYU'),
             ('UJNVEMI1U0QNEQBFOXROOPE2ZDHPZKTFDOAR4Q4FNGGQWDYJ', 'TYC3OFVJICZDRY2ROFCRH4OJEJIU0WOMRCUH5TSTBKVUF5EP'),
             ('5WCCP00O5EJYVALVKM2ZSV2R3GPNFIQH0LT4AZNQTUDGKAIC', 'EOO4AXGRYFEJE0RET4CQJWO0FSCHDERWQPIC0DG5IKU3FSA1'),
             ('CAJRMJ2G1UAEMWW15D53EVTS4Q4WLP4M4KBTREFGZ2NNOORS', 'Y24WTDBMC03NQLNMC2W2ESGF1C5IDNVWDZVMTO0PZW2REFP3'),
             ('YKM1SQVAHAI2ERVFQZNT1BXARDYSGBEACCAOKPTAWLMNVNCK', '2U0X5KPXABRQKNKB1VPTEWYN3SVA0NKMFC1VMQEGMPECEZFB')]

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
    """ Forms the request to send to the API and returns the data if no errors occured """
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
        except:
            print("Failed getting the response")
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
        score = 0.25 * checkin_ratio + 1.5 / math.sqrt(distance_ratio)
        place['score'] = score
        res.append((score, place))

    return [e[1] for e in sorted(res, key=lambda x: x[0], reverse=True)]


def get_place(venue_id):
    if not is_place_in_db(venue_id):
        print("place not in DB")
        get_complete_venue(venue_id)

    return get_complete_venue_from_db(venue_id)


def get_places(location, distance=50, limit=5):
    # check whether the location is within a search area
    if not is_location_in_db(location, distance):
        print("location {} not in database".format(location))
        get_all_places(location)
    else:
        print("location {} in database".format(location))

    places = get_places_from_db(location, distance, limit)
    return places


def get_venue(t):
    venue_id, d = t
    d[venue_id] = 'running'
    if is_place_in_db(venue_id):
        d[venue_id] = 'done'
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
                "origin": "foursquare-api"
            })
    return results


def get_autocomplete_from_db(location, query, distance=250, limit=8):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = ""
    data = None
    if query == "":
        query_string = """
        WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
        )
        SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, v3.latitude, v3.longitude,
               ST_Distance(ST_TRANSFORM(v3.geom, 3857), p.coords) as distance, v2.categories 
        FROM (
            SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories
            FROM (
                SELECT v.venue_id, v.nb_checkins, unnest(categories) as category_id
                FROM venues v, place p
                WHERE v.city <> '' 
                  AND ST_DWITHIN(ST_TRANSFORM(v.geom, 3857), p.coords, %s)
            ) v1 JOIN categories c ON c.category_id = v1.category_id
            GROUP BY venue_id
        ) v2 JOIN venues v3  ON v2.venue_id = v3.venue_id, place p
        ORDER BY nb_checkins DESC, distance ASC
        LIMIT %s;"""
        data = (location['lon'], location['lat'], distance, limit)
    else:
        query_string = """
        WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords, %s as name
        )
        SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, v3.latitude, v3.longitude, 
               word_similarity(v3.name, p.name) as sml, 
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
            "venueid": record['venue_id'],
            "placeid": "",
            "category": category,
            "city": record['city'],
            "address": record['address'],
            "latitude": record['latitude'],
            "longitude": record['longitude'],
            "checkins": record['nb_checkins'],
            "distance": record['distance'],
            "origin": "foursquare-cache"
        })

    return sort_place_score(results)


def get_place_with_name(location, query, distance=200):
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


def get_place_with_id(venue_id):
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
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """SELECT COUNT(*) FROM venues WHERE venue_id = %s;"""
    cursor.execute(query_string, (venue_id,))
    count = cursor.fetchone()[0]
    return count > 0


def get_places_from_db(location, distance=50, limit=5):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH place AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
    )
    SELECT v3.name, v3.city, v3.venue_id, v3.address, v3.nb_checkins, v3.latitude, v3.longitude, v2.categories, 
           v3.rating,v3.nb_likes, v3.price_tier, v3.nb_tips,
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

    return sort_place_score(places)


def is_location_in_db(location, distance=50):
    connection, cursor = utils.connect_to_db("foursquare")

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
    connection, cursor = utils.connect_to_db("foursquare")

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
    nb_req = 0
    while nb_req < NB_MAX_REQ and data and 'venue' not in data['response']:
        data = send_request(url)
        nb_req += 1

    if nb_req == NB_MAX_REQ:
        print('Could not retrieve venue {}'.format(venue_id))
        return {}

    venue = data['response']['venue']
    save_venue_to_db(venue)

    nb_tips = venue['stats'].get('tipCount', 0)
    if nb_tips > 0:
        tips = get_all_tips_per_venue(venue_id)
        for tip in tips:
            save_tip_to_db(tip, venue_id)

    return venue


def get_complete_venue_from_db(venue_id):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
        SELECT v.venue_id, v.name, v.nb_checkins, v.latitude, v.longitude, v.rating, v.price_tier, v.nb_likes, v.nb_tips,
        v.city, v.address, v.phrases, t.chains, t.categories
        FROM (
            SELECT v1.venue_id, array_agg(DISTINCT c.name ORDER BY c.name) as categories, 
                   array_agg(DISTINCT ch.name ORDER BY ch.name) as chains
            FROM (
                SELECT venue_id,
                unnest(v1.categories) as category_id,
                unnest(v1.chains) as chain_id
                FROM venues v1
                WHERE venue_id = %s
            ) v1 JOIN categories c ON c.category_id = v1.category_id
                 LEFT OUTER JOIN chains ch ON ch.chain_id = v1.chain_id
            GROUP BY v1.venue_id
        ) t JOIN venues v ON v.venue_id = t.venue_id
        ORDER BY v.nb_checkins DESC
        LIMIT 1;"""

    data = (venue_id,)

    cursor.execute(query_string, data)
    rec = cursor.fetchone()

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
        "location": {
            "lon": rec['longitude'],
            "lat": rec['latitude'],
            "city": rec['city'],
            "address": rec['address']
        },
        "tips": get_all_tips_per_venue_from_db(venue_id)
    }

    return place


def save_venue_to_db(venue):
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

    # Save the different chains
    if len(chains) > 0:
        for chain in venue['venueChains']:
            save_chain_to_db(chain)

    query_string = """INSERT INTO venues 
    (venue_id, categories, chains, phrases, postcode, address, city, rating, nb_checkins, nb_tips, 
    nb_likes, longitude, latitude, country, country_code, name, instagram, twitter, phone, facebook, 
    facebook_id, facebook_name, price_tier, price_message, price_currency, date_added, parent_id, description, geom) 
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
            ST_GeomFromText(%s, 4326))
    ON CONFLICT DO NOTHING;"""
    data = (venue_id, categories, chains, phrases, postcode, address, city, rating, nb_checkins, nb_tips,
            nb_likes, longitude, latitude, country, country_code, name, instagram, twitter, phone, facebook,
            facebook_id, facebook_name, price_tier, price_message, price_currency, date_added, parent_id, description, geom)

    cursor.execute(query_string, data)
    connection.commit()

    # get the parent
    if parent_id != "" and not is_place_in_db(parent_id):
        get_complete_venue(parent_id)


def save_chain_to_db(chain):
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


def save_categories_to_db():
    def save_categories(categories, parent_id):
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
    save_categories(categories, "")


def get_all_tips_per_venue(venue_id):
    url = BASE_URL + "venues/%s/tips" % venue_id
    offset = 0
    limit  = 150
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


def get_all_tips_per_venue_from_db(venue_id):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
            SELECT t.tip_id, t.created_at, t.text, t.nb_likes, t.justification, t.justification_type, t.user_id, 
                   u.firstname, u.lastname, u.gender
            FROM tips t JOIN users u ON u.user_id = t.user_id      
            WHERE t.venue_id = %s  
            ORDER BY t.created_at DESC;"""

    data = (venue_id,)

    cursor.execute(query_string, data)
    records = cursor.fetchall()

    return [dict(rec) for rec in records]


def save_tip_to_db(tip, venue_id):
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


def save_user_to_db(user):
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


def dump_categories_list():
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


def get_category(category_id):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT c1.name as name, c2.name as parent_name
    FROM categories c1
    JOIN categories c2 ON c1.parent_id = c2.category_id
    WHERE c1.category_id = %s;"""

    cursor.execute(query_string, (category_id,))
    return cursor.fetchone()['name']


def get_category_of_venue(venue_id):
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


def get_personal_information_of_venue(venue_id):
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


def autocomplete_location(location, query, distance=250, limit=10):
    if not is_location_in_db(location):
        return get_autocomplete(location, query, distance, limit)
    else:
        return get_autocomplete_from_db(location, query, distance, limit)


def get_all_places_within_location(location='', args='location'):

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
            res = is_place_in_db(venue_id)
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
    elif argument == 'find':
        if len(sys.argv) == 4:
            lon = sys.argv[2]
            lat = sys.argv[3]
            location = {"lon": lon, "lat": lat}
            fsq_places = get_places_from_db(location, 100, 5)
            print(fsq_places)
        else:
            print('Error - Please give lon lat arguments')
    else:
        print('Error - unknown argument provided ({})'.format(argument))
        sys.exit(0)

    # boundary, loc = utils.get_boundaries_from_location("Great Britain")
    # print(utils.boundary_to_geojson_polygon(boundary))

    # place = get_place(venue_id)
    # print(place['nb_tips'], len(place['tips']))
    # print("Done")
