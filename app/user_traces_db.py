import os
import time
import datetime
import foursquare
import psycopg2
import psycopg2.extras
from collections import OrderedDict

DB_HOSTNAME = "localhost"
if "DB_HOSTNAME" in os.environ:
    DB_HOSTNAME = os.environ.get("DB_HOSTNAME")


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
        connection = psycopg2.connect(host=DB_HOSTNAME, database="users", user="postgres", password="postgres")
        cursor = connection.cursor()
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
    connection = psycopg2.connect(host=DB_HOSTNAME, database="users", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
    INSERT INTO visits
    (user_id, visit_id, latitude, longitude, arrival, departure, place_id, day, confidence)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING;"""
    data = (visit['user_id'], visit['visit_id'], visit['latitude'], visit['longitude'], visit['arrival'],
            visit['departure'], visit['place_id'], visit['day'], visit['confidence'])
    cursor.execute(query_string, data)
    connection.commit()


def save_user_place_to_db(place):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="users", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    point = "POINT({} {})".format(place['longitude'], place['latitude'])

    query_string = """
    INSERT INTO places
    (osm_point_id, osm_polygon_id, venue_id, address, city, place_id, latitude, longitude, name, user_entered, geom, ssid, user_id)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s)
    ON CONFLICT DO NOTHING;"""
    data = (place['osm_point_id'], place['osm_polygon_id'], place['venue_id'], place['address'], place['city'],
            place['place_id'], place['latitude'], place['longitude'], place['name'], place['user_entered'], point,
            place['ssid'], place['user_id'])
    cursor.execute(query_string, data)
    connection.commit()


def save_user_move_to_db(move):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="users", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query_string = """

    INSERT INTO moves
    (move_id, user_id, activity, activity_confidence, arrival_place_id, departure_place_id, 
     arrival_date, departure_date, day)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING;"""
    data = (move['move_id'], move['user_id'], move['activity'], move['activity_confidence'],
            move['arrival_place_id'], move['departure_place_id'], move['arrival_date'],
            move['departure_date'], move['day'])
    cursor.execute(query_string, data)
    connection.commit()


def load_raw_points(user_id, day):
    # TODO: use the accuracy and SSID information
    connection = psycopg2.connect(host=DB_HOSTNAME, database="users", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

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
    connection = psycopg2.connect(host=DB_HOSTNAME, database="users", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
    SELECT p.place_id as placeid, p.latitude, p.longitude, p.name, p.city, p.address, 
           p.osm_point_id, p.osm_polygon_id, p.venue_id
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
        res['category'] = ", ".join(foursquare.get_category_of_venue(res['venue_id']))
        res['personalinfo'] = foursquare.get_personal_information_of_venue(res['venue_id'])
        del res['venue_id']
        del res['osm_point_id']
        del res['osm_polygon_id']
        print(res)
        result.append(res)
    return result


def load_user_visits(user_id, day):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="users", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
        SELECT visit_id as visitid, place_id as placeid, arrival, departure, confidence
        FROM visits
        WHERE day = %s AND user_id = %s
        ORDER BY arrival ASC;"""
    data = (day, user_id)
    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


def load_user_moves(user_id, day):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="users", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
        SELECT move_id as moveid, activity, arrival_place_id as arrivalplaceid, 
               departure_place_id as departureplaceid, departure_date as departuredate, arrival_date as arrivaldate
        FROM moves
        WHERE day = %s AND user_id = %s
        ORDER BY departure_date ASC;"""
    data = (day, user_id)
    cursor.execute(query_string, data)
    return [dict(record) for record in cursor]


if __name__ == '__main__':
    result = load_raw_points('2017-11-21', '1EE560B1-6054-4E2D-A64B-B9ACC3FA0761')
    print(result)
