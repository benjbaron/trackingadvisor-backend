import os
import time
import datetime
import psycopg2
import psycopg2.extras
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


def save_user_trace_to_db(trace_file):
    print("processing trace {}".format(trace_file))
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

            query_string = """
            INSERT INTO traces 
            (user_id, longitude, latitude, timestamp, timestamp_utc, day, accuracy, target_accuracy, speed, nb_steps, activity,
             activity_confidence, ssid, battery_level, battery_status, geom)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
            ON CONFLICT DO NOTHING;"""
            data = (user_id, latitude, longitude, timestamp_local, timestamp_utc, day, accuracy, target_accuracy,
                    speed, nb_steps, activity, activity_confidence, ssid, battery_level, battery_status, point)
            cursor.execute(query_string, data)

        connection.commit()


def save_user_visit_to_db(visit):
    connection, cursor = utils.connect_to_db("users")

    query_string = """
    INSERT INTO visits
    (user_id, latitude, longitude, arrival, departure, place_id, day, confidence)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (arrival, departure) DO UPDATE SET place_id=EXCLUDED.place_id 
    RETURNING visit_id;"""
    data = (visit['user_id'], visit['latitude'], visit['longitude'], visit['arrival'],
            visit['departure'], visit['place_id'], visit['day'], visit['confidence'])

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
    ON CONFLICT (name, user_id) DO UPDATE SET name=EXCLUDED.name
    RETURNING place_id;"""
    data = (place['osm_point_id'], place['osm_polygon_id'], place['venue_id'], place['address'], place['city'],
            place['latitude'], place['longitude'], place['name'], place['user_entered'], point,
            place['ssid'], place['user_id'], place['color'], place['type'], place['category'])

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
    (user_id, category_id, place_id, icon, name, description, source, explanation, privacy, visit_id)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (user_id, place_id, category_id, name) DO UPDATE SET user_id=EXCLUDED.user_id
    RETURNING pi_id;"""
    data = (pi.get('user_id', None), pi.get('category_id', None), pi.get('place_id', None),
            pi.get('icon', None), pi.get('name', None), pi.get('description', None), pi.get('source', None),
            pi.get('explanation', None), pi.get('privacy', None), pi.get('visit_id', None))

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
        (user_id, question, type, answer, visit_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, type, visit_id) DO UPDATE SET user_id=EXCLUDED.user_id
        RETURNING review_id;"""
        data = (review.get('user_id', None), review.get('question', None), review.get('type', None),
                review.get('answer', None), review.get('visit_id', None))

    else:
        # insert in table reviews_personal_information
        query_string = """
        INSERT INTO reviews_personal_information
        (user_id, question, type, answer, place_id, pi_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, type, pi_id) DO UPDATE SET user_id=EXCLUDED.user_id
        RETURNING review_id;"""
        data = (review.get('user_id', None), review.get('question', None), review.get('type', None),
                review.get('answer', None), review.get('place_id', None), review.get('pi_id', None))

    cursor.execute(query_string, data)
    review_id = cursor.fetchone()[0]
    connection.commit()
    return review_id


def save_user_review_challenge_to_db(review_challenge):
    connection, cursor = utils.connect_to_db("users")

    query_string = """
    INSERT INTO review_challenges
    (user_id, name, day, date, personal_information_ids)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING;"""
    data = (review_challenge['user_id'], review_challenge['name'],
            review_challenge['day'], review_challenge['date'], review_challenge['personal_information_ids'])

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
        WHERE v.user_id = %s AND v.day = %s
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


def load_user_visits(user_id, day):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT visit_id as vid, place_id as pid, arrival as a, departure as d, confidence as c
    FROM visits
    WHERE day = %s AND user_id = %s
    ORDER BY arrival ASC;"""
    data = (day, user_id)

    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


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
    SELECT review_challenge_id as rcid, name, day, date, 
           personal_information_ids as piids
    FROM review_challenges
    WHERE user_id = %s AND day = %s;"""
    data = (user_id, day)

    cursor.execute(query_string, data)
    review_challenges = [dict(record) for record in cursor]
    return review_challenges[0] if review_challenges else None


def get_user_place(user_id, location, place_type="place", distance=50, limit=1):
    connection, cursor = utils.connect_to_db("users", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH place AS (
          SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
        )
    SELECT place_id, address, venue_id, user_entered, ssid, latitude, longitude, city, name, type, category,
           ST_Distance(p.coords, ST_TRANSFORM(geom, 3857)) AS distance
    FROM places, place p
    WHERE user_id = %s AND type = %s AND ST_DWithin(ST_TRANSFORM(geom, 3857), p.coords, %s)      
    ORDER BY distance ASC
    LIMIT %s;"""
    data = (location['lon'], location['lat'], user_id, place_type, distance, limit)

    cursor.execute(query_string, data)
    places = [dict(record) for record in cursor]
    return places[0] if places else None


if __name__ == '__main__':
    result = load_raw_points('2017-11-21', '1EE560B1-6054-4E2D-A64B-B9ACC3FA0761')
    print(result)
