import os
import time
import datetime
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from collections import OrderedDict

import foursquare
import utils


def timestamp_from_string(s):
    if s == '':
        return 0
    if '.' in s:
        return time.mktime(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f %z").timetuple())
    return time.mktime(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").timetuple())


def timestamp_utc_from_string(s):
    if s == '':
        return 0
    if '.' in s:
        return time.mktime(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f %z").utctimetuple())
    return time.mktime(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").utctimetuple())


def datetime_from_timestamp(ts):
    return datetime.datetime.fromtimestamp(ts)


def day_from_string(s):
    if s == '':
        return ''
    return s.split(" ")[0]


def save_user_info_to_db(user):
    connection, cursor = utils.connect_to_db("users")

    query_string = """
    INSERT INTO users
    (ios_id, android_id, push_notification_id, name, email, country, birthday, date_added)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (ios_id) DO UPDATE SET ios_id=EXCLUDED.ios_id
    RETURNING user_id;"""
    data = (user.get('ios_id', None), user.get('android_id', None), user.get('push_notification_id', None),
            user.get('name', None), user.get('email', None), user.get('country', None), user.get('birthday', None),
            user.get('date_added', None))

    cursor.execute(query_string, data)
    user_id = cursor.fetchone()[0]
    connection.commit()
    return user_id


def save_user_trace_to_db(trace_file):
    days = set()
    uids = set()
    with open(trace_file, 'r') as f:
        connection, cursor = utils.connect_to_db("users")

        header = f.readline().strip().lower().split(',')
        for row in f:
            fields = dict(zip(header, row.strip().split(',')))
            user_id = fields.get('user', '')
            latitude = float(fields.get('lat', '0'))
            longitude = float(fields.get('lon', '0'))
            timestamp_local = timestamp_from_string(fields.get('timestamp', ''))
            timestamp_utc = timestamp_utc_from_string(fields.get('timestamp', ''))
            day = day_from_string(fields.get('timestamp', ''))
            accuracy = float(fields.get('accuracy', 0))
            target_accuracy = float(fields.get('targetaccuracy', 0))
            speed = float(fields.get('speed', 0))
            nb_steps = int(fields.get('nbsteps', 0))
            activity = fields.get('activity', '')
            activity_confidence = fields.get('activityconfidence', 0)
            ssid = fields.get('ssid', '')
            battery_level = fields.get('batterylevel', 0)
            battery_status = fields.get('batterycharge', '')
            point = "POINT({} {})".format(longitude, latitude)

            if user_id == '':
                continue

            days.add(day)
            uids.add(user_id)

            query_string = """
            INSERT INTO traces 
            (user_id, longitude, latitude, timestamp, timestamp_utc, day, accuracy, target_accuracy, speed, nb_steps, 
            activity, activity_confidence, ssid, battery_level, battery_status, geom)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
            ON CONFLICT DO NOTHING;"""
            data = (user_id, latitude, longitude, timestamp_local, timestamp_utc, day, accuracy, target_accuracy,
                    speed, nb_steps, activity, activity_confidence, ssid, battery_level, battery_status, point)
            cursor.execute(query_string, data)

        connection.commit()

    return list(uids), list(days)


def save_user_visit_to_db(visit):
    connection, cursor = utils.connect_to_db("users")

    print("save_user_visit, %s" % visit)

    query_string = """
    INSERT INTO visits
    (user_id, latitude, longitude, arrival, departure, place_id, day, confidence, original_arrival)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (original_arrival, user_id) DO UPDATE SET 
      departure = GREATEST(visits.departure, EXCLUDED.departure),
      arrival = EXCLUDED.arrival
    RETURNING visit_id;"""
    data = (visit.get('user_id', None), visit.get('latitude', None), visit.get('longitude', None),
            visit.get('arrival', None), visit.get('departure', None), visit.get('place_id', None),
            visit.get('day', None), visit.get('confidence', 1.0), visit.get('original_arrival', None))

    cursor.execute(query_string, data)
    visit_id = cursor.fetchone()[0]
    connection.commit()
    return visit_id


def save_user_place_to_db(place):
    connection, cursor = utils.connect_to_db("users")

    point = "POINT({} {})".format(place['longitude'], place['latitude'])

    query_string = """
    INSERT INTO places
    (osm_point_id, osm_polygon_id, venue_id, address, city, latitude, longitude, name, user_entered, geom, 
     ssid, user_id, color, type, category)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s)
    ON CONFLICT (user_id, venue_id) WHERE venue_id <> '' DO UPDATE SET user_id=EXCLUDED.user_id
    RETURNING place_id;"""
    data = (place.get('osm_point_id', None), place.get('osm_polygon_id', None), place.get('venue_id', ''),
            place.get('address', None), place.get('city', None), place.get('latitude', None), place.get('longitude', None),
            place.get('name', None), place.get('user_entered', None), point, place.get('ssid', None),
            place.get('user_id', None), place.get('color', None), place.get('type', None), place.get('category', None))

    cursor.execute(query_string, data)
    place_id = cursor.fetchone()[0]
    connection.commit()
    return place_id


def save_user_move_to_db(move):
    connection, cursor = utils.connect_to_db("users")

    query_string = """
    INSERT INTO moves
    (user_id, activity, activity_confidence, arrival_place_id, departure_place_id, 
     arrival_date, departure_date, day)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (arrival_place_id, departure_place_id, arrival_date, departure_date) DO UPDATE SET user_id=EXCLUDED.user_id
    RETURNING move_id ;"""
    data = (move['user_id'], move['activity'], move['activity_confidence'],
            move['arrival_place_id'], move['departure_place_id'], move['arrival_date'],
            move['departure_date'], move['day'])

    cursor.execute(query_string, data)
    move_id = cursor.fetchone()[0]
    connection.commit()
    return move_id


def save_user_personal_information_to_db(pi):
    connection, cursor = utils.connect_to_db("users")

    query_string = """
    INSERT INTO personal_information
    (user_id, category_id, place_id, icon, name, description, source, explanation, privacy, visit_id, explanation_comment)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (user_id, place_id, category_id, name) DO UPDATE SET user_id=EXCLUDED.user_id
    RETURNING pi_id;"""
    data = (pi.get('user_id', None), pi.get('category_id', None), pi.get('place_id', None), pi.get('icon', None),
            pi.get('name', None), pi.get('description', None), pi.get('source', None), pi.get('explanation', None),
            pi.get('privacy', None), pi.get('visit_id', None), pi.get('explanation_comment', None))

    cursor.execute(query_string, data)
    pi_id = cursor.fetchone()[0]
    connection.commit()
    return pi_id


def remove_all_personal_information_categories_in_db():
    connection, cursor = utils.connect_to_db("users")
    cursor.execute("DELETE FROM personal_information_categories")
    connection.commit()


def save_user_personal_information_category_to_db(pi_cat):
    connection, cursor = utils.connect_to_db("users")

    query_string = """
    INSERT INTO personal_information_categories
    (icon, name, description, acronym)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT DO NOTHING
    RETURNING category_id;"""
    data = (pi_cat['icon'], pi_cat['name'], pi_cat['description'], pi_cat['acronym'])

    print("acronym: {}".format(pi_cat['acronym']))
    cursor.execute(query_string, data)
    category_id = cursor.fetchone()[0]
    connection.commit()
    return category_id


def save_user_reviews_to_db(review):
    connection, cursor = utils.connect_to_db("users")

    query_string = ""
    data = None

    if review['type'] == 0:
        # insert in table reviews_visits
        query_string = """
        INSERT INTO reviews_visits
        (user_id, question, type, answer, visit_id, date_added)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, type, visit_id) DO UPDATE SET user_id=EXCLUDED.user_id
        RETURNING review_id;"""
        data = (review.get('user_id', None), review.get('question', None), review.get('type', None),
                review.get('answer', None), review.get('visit_id', None), int(time.time()))

    else:
        # insert in table reviews_personal_information
        query_string = """
        INSERT INTO reviews_personal_information
        (user_id, question, type, answer, place_id, pi_id, date_added)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, type, pi_id) DO UPDATE SET user_id=EXCLUDED.user_id
        RETURNING review_id;"""
        data = (review.get('user_id', None), review.get('question', None), review.get('type', None),
                review.get('answer', None), review.get('place_id', None), review.get('pi_id', None), int(time.time()))

    cursor.execute(query_string, data)
    review_id = cursor.fetchone()[0]
    connection.commit()
    return review_id


def save_user_review_challenge_to_db(review_challenge):
    connection, cursor = utils.connect_to_db("users")

    query_string = """
    INSERT INTO review_challenges
    (user_id, day, date_created, personal_information_id, visit_id, place_id, place_number)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (day, user_id, place_id, place_number) DO UPDATE SET user_id=EXCLUDED.user_id
    RETURNING review_challenge_id;"""
    data = (review_challenge.get('user_id', None), review_challenge.get('day', None),
            review_challenge.get('date_created', None), review_challenge.get('personal_information_id', None),
            review_challenge.get('visit_id', None), review_challenge.get('place_id', None),
            review_challenge.get('place_number', None))

    cursor.execute(query_string, data)
    review_challenge_id = cursor.fetchone()[0]
    connection.commit()
    return review_challenge_id


def load_raw_points(user_id, day):
    # TODO: use the accuracy and SSID information
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT longitude, latitude, timestamp
    FROM traces
    WHERE day = %s AND user_id = %s
    ORDER BY timestamp ASC;"""
    data = (day, user_id)
    cursor.execute(query_string, data)
    records = cursor.fetchall()
    result = []
    for rec in records:
        result.append([rec['longitude'], rec['latitude'], rec['timestamp']])

    return result


def load_user_places(user_id, day):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT p.place_id as pid, p.latitude as lat, p.longitude as lon, p.name as name, p.city as c, p.address as a, 
           p.venue_id as vid, p.type as t, p.color as col
    FROM (
        SELECT p1.place_id
        FROM visits v
        JOIN places p1 ON p1.place_id = v.place_id
        WHERE v.user_id = %s AND v.day = %s AND v.deleted <> TRUE
        GROUP BY p1.place_id
    ) t JOIN places p ON t.place_id = p.place_id;"""
    data = (user_id, day)

    cursor.execute(query_string, data)
    result = []
    for record in cursor:
        res = dict(record)
        cat = foursquare.get_category_of_venue(res['vid'])
        res['cat'] = ", ".join(e['name'] for e in cat)
        result.append(res)
    return result


def load_user_place(user_id, place_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT p.place_id as pid, p.latitude as lat, p.longitude as lon, p.name as name, p.city as c, p.address as a, 
           p.venue_id as vid, p.type as t, p.color as col
    FROM places p
    WHERE place_id = %s AND user_id = %s;"""
    data = (place_id, user_id)

    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return dict(res) if res else {}


def load_user_visits(user_id, day):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT visit_id as vid, place_id as pid, arrival as a, departure as d, confidence as c
    FROM visits
    WHERE day = %s AND user_id = %s AND deleted <> TRUE
    ORDER BY arrival ASC;"""
    data = (day, user_id)

    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


def load_user_visits_at_place(user_id, place_id, day):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
        SELECT visit_id as vid, place_id as pid, arrival as a, original_arrival as oa
        FROM visits
        WHERE day = %s AND user_id = %s AND deleted <> TRUE AND place_id = %s
        ORDER BY arrival ASC;"""
    data = (day, user_id, place_id)

    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


def load_user_visit(user_id, visit_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT visit_id as vid, place_id as pid, arrival as a, departure as d, confidence as c
    FROM visits 
    WHERE visit_id = %s AND user_id = %s;"""
    data = (visit_id, user_id)

    cursor.execute(query_string, data)
    return dict(cursor.fetchone())


def load_user_moves(user_id, day):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT move_id as mid, activity as a, arrival_place_id as apid, 
           departure_place_id as dpid, departure_date as dd, arrival_date as ad
    FROM moves
    WHERE day = %s AND user_id = %s
    ORDER BY departure_date ASC;"""
    data = (day, user_id)

    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


def load_user_review_visit(user_id, visit_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT review_id as rid, question as q, type as t, answer as a, visit_id as vid
    FROM reviews_visits
    WHERE user_id = %s AND visit_id = %s;"""
    data = (user_id, visit_id)

    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


def load_user_review_pi(user_id, pi_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT review_id as rid, question as q, type as t, answer as a, place_id as pid, pi_id as piid
    FROM reviews_personal_information
    WHERE user_id = %s AND pi_id = %s;"""
    data = (user_id, pi_id)

    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


def load_user_personal_information(user_id, place_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT pi_id as piid, category_id as picid, 
           place_id as pid, icon, name, description as d, source as s, explanation as e, privacy as p
    FROM personal_information
    WHERE user_id = %s AND place_id = %s;"""
    data = (user_id, place_id)

    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


def load_user_personal_information_from_id(user_id, pi_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
        SELECT pi_id as piid, category_id as picid, 
               place_id as pid, icon, name, description as d, source as s, explanation as e, privacy as p
        FROM personal_information
        WHERE user_id = %s AND pi_id = %s;"""
    data = (user_id, pi_id)

    cursor.execute(query_string, data)
    pis = [dict(record) for record in cursor]
    return pis[0] if pis else None


def load_personal_information_categories(category_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT category_id as picid, icon, name, d
    FROM personal_information_categories
    WHERE category_id = %s;"""
    data = (category_id,)

    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


def load_user_review_challenge(user_id, day):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT review_challenge_id as rcid, day, date_created as d, 
           personal_information_id as piid, visit_id as vid, place_id as pid
    FROM review_challenges
    WHERE user_id = %s AND day = %s;"""
    data = (user_id, day)

    cursor.execute(query_string, data)
    review_challenges = [dict(record) for record in cursor]
    return review_challenges


def get_user_place(user_id, location, distance=50, limit=1):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
        )
    SELECT place_id, address, venue_id, user_entered, ssid, latitude, longitude, city, name, type, category, color,
           ST_Distance(p.coords, ST_TRANSFORM(geom, 3857)) AS distance
    FROM places, place p
    WHERE user_id = %s AND ST_DWithin(ST_TRANSFORM(geom, 3857), p.coords, %s)      
    ORDER BY distance ASC
    LIMIT %s;"""
    data = (location['lon'], location['lat'], user_id, distance, limit)

    cursor.execute(query_string, data)
    places = [dict(record) for record in cursor]
    return places


def autocomplete_location(user_id, location, query, distance=50, limit=5):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    places = []
    if query == "":
        places = get_user_place(user_id, location, distance, limit)
    else:
        query_string = """
            WITH place AS (
                  SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords, %s as name
                )
            SELECT pp.place_id, pp.address, pp.venue_id, pp.user_entered, pp.ssid, pp.latitude, pp.longitude, pp.city, 
                   pp.name, pp.type, pp.category, pp.color, ST_Distance(p.coords, ST_TRANSFORM(pp.geom, 3857)) AS distance, 
                   word_similarity(pp.name, p.name) AS sml 
            FROM places pp, place p
            WHERE pp.user_id = %s AND p.name <%% pp.name  AND ST_DWithin(ST_TRANSFORM(pp.geom, 3857), p.coords, %s)      
            ORDER BY sml DESC, distance ASC
            LIMIT %s;"""
        data = (location['lon'], location['lat'], query, user_id, distance, limit)

        cursor.execute(query_string, data)
        places = [dict(record) for record in cursor]

    results = []
    for place in places:
        results.append({
            "name": place['name'],
            "venueid": place['venue_id'],
            "placeid": place['place_id'],
            "category": place['category'] if place['category'] else "",
            "city": place['city'],
            "score": place.get('sml', 1.0),
            "address": place['address'],
            "latitude": place['latitude'],
            "longitude": place['longitude'],
            "checkins": 0,
            "distance": place['distance'],
            "origin": "user-places"
        })

    return results


def load_user_info(user_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
        SELECT *
        FROM users
        WHERE user_id = %s;"""

    cursor.execute(query_string, (user_id,))
    return dict(cursor.fetchone())


def get_raw_trace(user_id, start, end):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT longitude as lon, latitude as lat, timestamp as ts 
    FROM traces 
    WHERE user_id = %s AND timestamp BETWEEN %s AND %s;"""
    data = (user_id, start, end)

    cursor.execute(query_string, data)
    places = [dict(record) for record in cursor]
    return places


def get_user_reviews_for_visit(user_id, visit_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT v.visit_id, pi.pi_id, rpi.review_id, rpi.answer, rpi.type
    FROM visits v 
    INNER JOIN personal_information pi ON (pi.place_id = v.place_id AND pi.user_id = v.user_id)
    INNER JOIN reviews_personal_information rpi ON (rpi.pi_id = pi.pi_id AND rpi.user_id = pi.user_id)
    WHERE v.user_id = %s AND v.visit_id = %s;"""
    cursor.execute(query_string, (user_id, visit_id))

    reviews_pi = [dict(record) for record in cursor]

    query_string = """
    SELECT v.visit_id, rv.review_id, rv.answer, rv.type
    FROM visits v 
    INNER JOIN reviews_visits rv ON (rv.visit_id = v.visit_id AND rv.user_id = v.user_id)
    WHERE v.user_id = %s AND v.visit_id = %s;"""
    cursor.execute(query_string, (user_id, visit_id))

    reviews = [dict(record) for record in cursor]
    review_visit = reviews[0] if reviews else None

    return review_visit, reviews_pi


def delete_all_records(user_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    for table in ['moves', 'visits', 'places', 'traces', 'review_challenges', 'reviews_visits',
                  'reviews_personal_information', 'personal_information']:
        cursor.execute(sql.SQL("DELETE FROM {} WHERE user_id = %s").format(sql.Identifier(table)), (user_id,))

    connection.commit()
    print("Done deleting database entries for user %s" % user_id)


def delete_user_visit(user_id, visit_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)
    cursor.execute(sql.SQL("UPDATE visits SET deleted = true WHERE user_id = %s AND visit_id = %s"),
                   (user_id, visit_id))
    connection.commit()


def delete_user_place(user_id, place_id, visit_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    # check if the place is associated to other visits
    # /!\ IMPORTANT
    cursor.execute(sql.SQL("SELECT visit_id FROM visits WHERE user_id = %s AND place_id = %s "),
                   (user_id, place_id))
    records = cursor.fetchall()
    if len(records) != 1 and records[0] != visit_id:
        return

    # delete the place
    cursor.execute(sql.SQL("DELETE FROM places WHERE user_id = %s AND place_id = %s"),
                   (user_id, place_id))

    # delete all the personal information associated to this place
    cursor.execute(sql.SQL("DELETE FROM personal_information WHERE user_id = %s AND place_id = %s"),
                   (user_id, place_id))

    # delete all the reviews associated to this place
    cursor.execute(sql.SQL("DELETE FROM reviews_personal_information WHERE user_id = %s AND place_id = %s"),
                   (user_id, place_id))
    connection.commit()


def update_user_info(user):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    UPDATE users SET
      push_notification_id = COALESCE(%s, push_notification_id),
      ios_id = COALESCE(%s, ios_id),
      android_id = COALESCE(%s, android_id),
      name = COALESCE(%s, name),
      email = COALESCE(%s, email),
      birthday = COALESCE(%s, birthday),
      country = COALESCE(%s, birthday),
      date_added = COALESCE(%s, date_added)
    WHERE user_id = %s;"""
    data = (user.get('push_notification_id', None), user.get('ios_id', None), user.get('android_id', None),
            user.get('name', None), user.get('email', None), user.get('birthday', None), user.get('country', None),
            user.get('date_added', None), user.get('user_id', ''))

    cursor.execute(query_string, data)
    connection.commit()


def update_user_visit(visit):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    UPDATE visits SET 
      latitude = COALESCE(%s, latitude), 
      longitude = COALESCE(%s, longitude), 
      arrival = COALESCE(%s, arrival), 
      departure = COALESCE(%s, departure),
      place_id = COALESCE(%s, place_id),
      confidence = COALESCE(%s, confidence)
    WHERE user_id = %s AND visit_id = %s;"""
    data = (visit.get('latitude', None), visit.get('longitude', None), visit.get('arrival', None),
            visit.get('departure', None), visit.get('place_id', None), visit.get('confidence', 1.0),
            visit.get('user_id', ''), visit.get('visit_id', ''))

    cursor.execute(query_string, data)
    connection.commit()


def update_user_place(place):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    UPDATE places SET 
      latitude = COALESCE(%s, latitude), 
      longitude = COALESCE(%s, longitude), 
      name = COALESCE(%s, name), 
      address = COALESCE(%s, address), 
      city = COALESCE(%s, city)
    WHERE user_id = %s AND place_id = %s;"""
    data = (place.get('latitude', None), place.get('longitude', None), place.get('name', None), place.get('address', None),
            place.get('city', None), place.get('user_id', ''), place.get('place_id', ''))

    cursor.execute(query_string, data)
    connection.commit()


def is_review_visit(review_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)
    query_string = """SELECT COUNT(*) FROM reviews_visits WHERE review_id = %s;"""
    cursor.execute(query_string, (review_id,))
    count = cursor.fetchone()[0]
    return count > 0


def is_review_pi(review_id):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)
    query_string = """SELECT COUNT(*) FROM reviews_personal_information WHERE review_id = %s;"""
    cursor.execute(query_string, (review_id,))
    count = cursor.fetchone()[0]
    return count > 0


def update_user_review(review):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    review_id = review['review_id']
    table = ""
    if is_review_pi(review_id):
        table = "reviews_personal_information"
    elif is_review_visit(review_id):
        table = "reviews_visits"
    else:
        return

    print("review %s - table %s - answer %s" % (review_id, table, review['answer']))

    query_string = sql.SQL("""UPDATE {} SET 
      question = COALESCE(%s, question),
      type = COALESCE(%s, type),
      answer = COALESCE(%s, answer),
      date_reviewed = COALESCE(%s, date_reviewed)
    WHERE user_id = %s AND review_id = %s""").format(sql.Identifier(table))
    data = (review.get('question', None), review.get('type', None), review.get('answer', None), int(time.time()),
            review.get('user_id', ''), review.get('review_id', ''))

    cursor.execute(query_string, data)
    connection.commit()


def update_user_review_visit(review):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    UPDATE reviews_visits SET
      question = COALESCE(%s, question),
      type = COALESCE(%s, type),
      answer = COALESCE(%s, answer),
      date_reviewed = COALESCE(%s, date_reviewed)
    WHERE user_id = %s AND visit_id = %s;"""
    data = (review.get('question', None), review.get('type', None), review.get('answer', None), int(time.time()),
            review.get('user_id', ''), review.get('visit_id', ''))

    cursor.execute(query_string, data)
    connection.commit()


def update_user_personal_information(pi):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    UPDATE personal_information SET
      icon = COALESCE(%s, icon),
      name = COALESCE(%s, name),
      description = COALESCE(%s, description),
      explanation = COALESCE(%s, explanation),
      privacy = COALESCE(%s, privacy),
      place_id = COALESCE(%s, place_id),
      category_id = COALESCE(%s, category_id),
      source = COALESCE(%s, source),
      visit_id = COALESCE(%s, visit_id),
      explanation_comment = COALESCE(%s, explanation_comment)
    WHERE user_id = %s AND pi_id = %s;"""
    data = (pi.get('icon', None), pi.get('name', None), pi.get('description', None), pi.get('explanation', None),
            pi.get('privacy', None), pi.get('place_id', None), pi.get('category_id', None), pi.get('source', None),
            pi.get('visit_id', None), pi.get('explanation_comment', None), pi.get('user_id', ''), pi.get('pi_id', ''))

    cursor.execute(query_string, data)
    connection.commit()


def update_user_review_pi(review):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    UPDATE reviews_personal_information SET
      question = COALESCE(%s, question),
      type = COALESCE(%s, type),
      answer = COALESCE(%s, answer),
      date_reviewed = COALESCE(%s, date_reviewed)
    WHERE user_id = %s AND pi_id = %s;"""
    data = (review.get('question', None), review.get('type', None), review.get('answer', None), int(time.time()),
            review.get('user_id', ''), review.get('pi_id', ''))

    cursor.execute(query_string, data)
    connection.commit()


def update_user_challenge(challenge):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
        UPDATE review_challenges SET
          day = COALESCE(%s, day),
          date_created = COALESCE(%s, date_created),
          date_completed = COALESCE(%s, date_completed),
          personal_information_id = COALESCE(%s, personal_information_id),
          visit_id = COALESCE(%s, visit_id),
          place_id = COALESCE(%s, place_id)
        WHERE user_id = %s AND review_challenge_id = %s;"""
    data = (challenge.get('day', None), challenge.get('date_created', None), challenge.get('date_completed', None),
            challenge.get('personal_information_id', None), challenge.get('visit_id', None),
            challenge.get('place_id', None), challenge.get('user_id', None),  challenge.get('review_challenge_id', None))

    print(data)

    cursor.execute(query_string, data)
    connection.commit()


if __name__ == '__main__':
    result = load_raw_points('2017-11-21', '1EE560B1-6054-4E2D-A64B-B9ACC3FA0761')
    print(result)
