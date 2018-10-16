from psycopg2 import sql
import psycopg2
import time

import utils
import foursquare

BASE_URL = "https://api.foursquare.com/v2/"

# getting the database connection information
connection = None
cursor = None

pis = foursquare.load_personal_information()


def get_db_connection():
    global cursor, connection
    if cursor is None or connection is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    # Test the liveliness of the connection.
    try:
        cursor.execute("SELECT 1")
    except psycopg2.OperationalError:
        # Reconnect to the database.
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)


def get_fq_fulladdress(address, city):
    get_db_connection()

    if city != '' and address != '':
        return "%s, %s" % (address, city)
    else:
        return "%s%s" % (address, city)


def format_fq_venue(venue):
    venue_id = venue['id']
    address = venue['location']['address'] if 'address' in venue['location'] else ''
    city = venue['location']['city'] if 'city' in venue['location'] else ''
    fulladdress = get_fq_fulladdress(address, city)
    categories = [c for c in venue['categories'] if 'primary' in c and c['primary']]
    category = {}
    if len(categories) > 0:
        category = categories[0]
        emoji, icon = foursquare.get_icon_for_venue(venue_id, {'categories': [category['id']]}, connection=connection, cursor=cursor)
    else:
        emoji, icon = '👣', 'map-marker'

    return {
        'fulladdress': fulladdress,
        'address': address,
        'city': city,
        'category': category.get('name', ''),
        'lat': venue['location']['lat'],
        'lon': venue['location']['lng'],
        'name': venue['name'],
        'id': venue_id,
        'icon': icon
    }


def get_fq_place(venue_id):
    url = BASE_URL + "venues/" + venue_id
    data = foursquare.send_request(url)

    if data is None or 'response' not in data or 'venue' not in data['response']:
        return {}

    venue = data['response']['venue']
    return format_fq_venue(venue)


def get_places(query, location, bounds, limit=50):
    get_db_connection()

    url = BASE_URL + "venues/search"
    params = {
        "ne": "%s,%s" % (bounds['ne']['lat'], bounds['ne']['lon']),
        "sw": "%s,%s" % (bounds['sw']['lat'], bounds['sw']['lon']),
        "limit": str(limit),
        "query": query,
        "intent": "browse"
    }

    data = foursquare.send_request(url, params)
    results = []

    if data is None or 'response' not in data or 'venues' not in data['response']:
        return results

    for venue in data['response']['venues']:
        results.append(format_fq_venue(venue))

    return results


def geocode_autocomplete(query):
    url = BASE_URL
    url += "geo/geocode"
    params = {
        "autocomplete": "true",
        "allowCountry": "false",
        "maxInterpretations": "10",
        "locale": "en",
        "explicit-lang": "true",
        "query": query
    }

    data = foursquare.send_request(url, params)
    results = []

    if 'response' not in data or 'geocode' not in data['response']:
        return results

    if 'interpretations' not in data['response']['geocode']:
        return results

    if 'items' not in data['response']['geocode']['interpretations']:
        return results

    for geo in data['response']['geocode']['interpretations']['items']:
        results.append({
            "name": geo['feature']['displayName'],
            "id": geo['feature']['id'],
            "geometry": geo['feature']['geometry']
        })

    return results


def start_session(session_id, ip_address):
    connection, cursor = utils.connect_to_db("study")

    query_string = """INSERT INTO sessions 
    (session_start, session_id, ip_address)
    VALUES (%s, %s, %s)
    ON CONFLICT DO NOTHING;"""
    data = (utils.current_timestamp(), session_id, ip_address)

    cursor.execute(query_string, data)
    connection.commit()


def add_trackingadvisor_id(session_id, user_id):
    connection, cursor = utils.connect_to_db("study")

    query_string = """UPDATE sessions SET user_id = %s WHERE session_id = %s;"""
    data = (user_id, session_id)

    cursor.execute(query_string, data)
    connection.commit()


def end_session(session_id):
    connection, cursor = utils.connect_to_db("study")

    query_string = """UPDATE sessions SET session_end = %s WHERE session_id = %s;"""
    data = (utils.current_timestamp(), session_id)

    cursor.execute(query_string, data)
    connection.commit()


def save_place(session_id, place):
    connection, cursor = utils.connect_to_db("study")

    place_id = place['id']
    icon = place['icon-name']
    place_name = place['name']
    lon = place['lon']
    lat = place['lat']
    address = place['address']
    city = place['city']
    fulladdress = place['fulladdress']
    category = place['category']

    query_string = """INSERT INTO places 
    (place_id, session_id, place_name, longitude, latitude, address, city, category, fulladdress, icon)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (session_id, place_id) DO UPDATE SET 
      place_name=EXCLUDED.place_name, 
      longitude=EXCLUDED.longitude,
      latitude=EXCLUDED.latitude,
      address=EXCLUDED.address,
      city=EXCLUDED.city,
      category=EXCLUDED.category,
      fulladdress=EXCLUDED.fulladdress,
      icon=EXCLUDED.icon;"""

    data = (place_id, session_id, place_name, lon, lat, address, city, category, fulladdress, icon)

    cursor.execute(query_string, data)
    connection.commit()


def udpate_place(place_id, place):
    connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)
    query = sql.SQL("""UPDATE places SET 
                         category = %s, 
                         latitude = %s, 
                         longitude = %s, 
                         address = %s, 
                         city = %s, icon = %s, 
                         fulladdress = %s 
                       WHERE place_id = %s""")
    data = (place['category'], place['lat'], place['lon'], place['address'], place['city'], place['icon'], place['fulladdress'], place_id)
    cursor.execute(query, data)
    connection.commit()


def save_personal_information_relevance(session_id, place_id, pi_id, rating):
    connection, cursor = utils.connect_to_db("study")

    query_string = """INSERT INTO place_personal_information_relevance 
        (pi_id, place_id, session_id, rating)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (session_id, place_id, pi_id) DO UPDATE SET rating=EXCLUDED.rating;"""
    data = (pi_id, place_id, session_id, rating)

    cursor.execute(query_string, data)
    connection.commit()


def save_personal_information_importance(session_id, place_id, pi_id, rating):
    connection, cursor = utils.connect_to_db("study")

    query_string = """INSERT INTO place_personal_information_importance 
            (pi_id, place_id, session_id, rating)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (session_id, place_id, pi_id) DO UPDATE SET rating=EXCLUDED.rating;"""
    data = (pi_id, place_id, session_id, rating)

    cursor.execute(query_string, data)
    connection.commit()


def save_personal_information_privacy(session_id, pi_id, rating):
    connection, cursor = utils.connect_to_db("study")

    query_string = """INSERT INTO place_personal_information_privacy
        (pi_id, session_id, rating)
        VALUES (%s, %s, %s)
        ON CONFLICT (session_id, pi_id) DO UPDATE SET rating=EXCLUDED.rating;"""
    data = (pi_id, session_id, rating)

    cursor.execute(query_string, data)
    connection.commit()


def save_place_question(session_id, place_id, t, rating):
    connection, cursor = utils.connect_to_db("study")

    col = 'know_rating' if t == 'q1' else 'private_rating'

    query_string = sql.SQL("UPDATE places SET {} = %s WHERE session_id = %s AND place_id = %s;").format(sql.Identifier(col))
    data = (rating, session_id, place_id)

    cursor.execute(query_string, data)
    connection.commit()


# Retrieve statistics from the database
def get_nb_distinct_sessions(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("SELECT COUNT(DISTINCT session_id) FROM places;")
    cursor.execute(query_string)
    return cursor.fetchone()[0]


def get_nb_distinct_finished_sessions(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("SELECT COUNT(DISTINCT session_id) FROM sessions WHERE session_start IS NOT NULL AND session_end IS NOT NULL;")
    cursor.execute(query_string)
    return cursor.fetchone()[0]


def get_avg_session_duration(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL(
        """SELECT AVG(session_end-session_start) / 60 as avg
           FROM sessions
           WHERE session_start IS NOT NULL AND session_end IS NOT NULL AND session_end-session_start < 3600;""")
    cursor.execute(query_string)
    return cursor.fetchone()[0]


def get_avg_nb_places_per_user(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("""SELECT AVG(q.c)
                              FROM (SELECT COUNT(place_id) as c
                                  FROM places
                                  GROUP BY session_id) as q;""")
    cursor.execute(query_string)
    return cursor.fetchone()[0]


def get_nb_distinct_places(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("SELECT COUNT(DISTINCT  place_id) FROM places;")
    cursor.execute(query_string)
    return cursor.fetchone()[0]


def user_stats(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("""
      SELECT COUNT(p.place_id) as nb_places, s.ip_address, s.session_start, s.session_end
      FROM places p JOIN sessions s ON s.session_id = p.session_id
      GROUP BY s.session_id, s.ip_address, s.session_start, s.session_end;""")
    cursor.execute(query_string)
    res = []
    for record in cursor:
        res.append({
            'nb_places': record['nb_places'],
            'ip_address': record['ip_address'],
            'start': 'N/A' if record['session_start'] is None else utils.datetime_from_timestamp(record['session_start']).strftime("%Y-%m-%d %H:%M:%S"),
            'end': 'N/A' if record['session_end'] is None else utils.datetime_from_timestamp(record['session_end']).strftime("%Y-%m-%d %H:%M:%S")
        })

    return res


def get_all_places(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("""SELECT * FROM places;""")
    cursor.execute(query_string)
    return [dict(record) for record in cursor]


def get_all_distinct_place_ids(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("SELECT DISTINCT place_id FROM places;")
    cursor.execute(query_string)
    return [record['place_id'] for record in cursor]


def get_all_distinct_selected_places(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("""
          SELECT DISTINCT  p2.place_id, p2.place_name, p1.know_rating, p1.private_rating, p2.longitude, p2.latitude,
                           p2.address, p2.city, p2.fulladdress, p2.icon, p2.category
          FROM (SELECT place_id,
              array_agg(know_rating) FILTER (WHERE know_rating IS NOT NULL) as know_rating, 
              array_agg(private_rating) FILTER (WHERE private_rating IS NOT NULL) as private_rating
          FROM places
          GROUP BY place_id) as p1 
          JOIN places p2 ON p1.place_id = p2.place_id;""")
    cursor.execute(query_string)
    return dict([(record['place_id'], dict(record)) for record in cursor])


def get_stats():
    connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    return {
        'users': user_stats(connection=connection, cursor=cursor),
        'nb_total_users': get_nb_distinct_sessions(connection=connection, cursor=cursor),
        'nb_finished_sessions': get_nb_distinct_finished_sessions(connection=connection, cursor=cursor),
        'avg_completion_time': get_avg_session_duration(connection=connection, cursor=cursor),
        'nb_total_places': get_nb_distinct_places(connection=connection, cursor=cursor),
        'nb_avg_places_per_user': get_avg_nb_places_per_user(connection=connection, cursor=cursor)
    }


def update_place_records():
    print("Updating place records")
    places = get_all_places()
    for place in places:
        place_id = place['place_id']
        place = get_fq_place(place_id)
        print("Updating place %s (%s)" % (place['name'], place_id))
        udpate_place(place_id, place)


def get_relevance_ratings(place_id, connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query = sql.SQL("""SELECT pi_id, array_agg(rating) as ratings
               FROM place_personal_information_relevance
               WHERE place_id = %s
               GROUP BY pi_id;""")

    data = (place_id,)
    cursor.execute(query, data)
    res = {}
    for record in cursor:
        pi_id = record['pi_id']
        ratings = record['ratings']
        avg_rating = sum(r for r in ratings) / len(ratings)
        res[pi_id] = {
            "pi_id": pi_id,
            "ratings": ratings,
            "name": pis[pi_id]['name'],
            "avg_rating": avg_rating,
            "category_id": pis[pi_id]['category_id'],
            "subcategory_name": pis[pi_id]['subcategory_name'],
            "category_icon": pis[pi_id]['category_icon'],
            "tags": pis[pi_id]['tags']
        }
    return res


def get_model_stats():
    start_time = time.time()
    c_study, cur_study = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)
    c_fsq, cur_fsq = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    print("init - %s" % (time.time() - start_time))

    models = {}

    start_time = time.time()
    place_ids = get_all_distinct_place_ids(c_study, cur_study)
    print("got %s place ids" % len(place_ids))

    for place_id in place_ids:
        # 1 - get the personal information relevance information
        ratings = get_relevance_ratings(place_id, connection=c_study, cursor=cur_study)

        # 2 - get the personal information computed by the models for this place
        start_time = time.time()
        pis = foursquare.get_place_personal_information_from_db(place_id, connection=c_fsq, cursor=cur_fsq)

        # 3 - aggregate per model
        # a model is defined by (model_type, feature_type, avg, phrase_modeler)
        for pi in pis:
            pi_id = pi['pi_id']
            rank = pi['rank']
            model = (pi['model_type'], pi['feature_type'], pi['avg'], pi['phrase_modeler'])

            if model not in models:
                models[model] = [[0] * 5 for _ in range(10)]

            rating = [] if pi_id not in ratings else ratings[pi_id]['ratings']
            for r in rating:
                models[model][rank][r-1] += 1

    print("end - %s" % (time.time() - start_time))

    return models

