import sys
import psycopg2
import psycopg2.extras
import time
import random
import datetime
import json, requests
import math

DB_HOSTNAME = "colossus07"
NB_MAX_CONN = 25


def connect_to_db(database_name, cursor_type=None):
    nb_req = 0
    while nb_req < NB_MAX_CONN:
        try:
            connection = psycopg2.connect(host=DB_HOSTNAME, database=database_name, user="postgres", password="postgres")
            if cursor_type:
                cursor = connection.cursor(cursor_factory=cursor_type)
            else:
                cursor = connection.cursor()
        except psycopg2.Error as e:
            nb_req += 1
            time.sleep(random.uniform(0.1, 1.0))
        else:
            return connection, cursor

    print("Error connecting the database")
    sys.exit(0)


def print_progress(s):
    sys.stdout.write("\r\x1b[K" + s)
    sys.stdout.flush()


def get_osm_polygon_feature_from_name_and_housename(name, location, distance=50):
    print("getting polygon from name {} within {} of {}".format(name, location, distance))

    connection, cursor = connect_to_db("osm", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH venue AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as point, %s as name
    )
    SELECT *, GREATEST(k.sml1, k.sml2) as sml

    FROM (
      SELECT p.osm_id, p.name, p."addr:housename", v.name, word_similarity(v.name, p.name) as sml1, 
             word_similarity(v.name, p."addr:housename") as sml2, ST_Transform(way, 4326) as poly
      FROM planet_osm_polygon p, venue v
      WHERE (p.name %% v.name OR p."addr:housename" %% v.name)
            AND ST_DWITHIN(p.way, v.point, %s)
            AND p.admin_level IS NULL AND p.way_area < 500000.0
      ) k
    ORDER BY sml DESC;"""

    data = (location['lon'], location['lat'], name, distance)
    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return dict(res) if res else {}


def get_osm_polygon_feature_from_name(name, location, distance=50):
    connection, cursor = connect_to_db("osm", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH venue AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as point, %s as name
    )

    SELECT p.osm_id, p.name, v.name, word_similarity(v.name, p.name) as sml, 
           ST_Transform(way, 4326) as poly
    FROM planet_osm_polygon p, venue v
    WHERE (p.name %% v.name)
          AND ST_DWITHIN(p.way, v.point, %s)
          AND p.admin_level IS NULL AND p.way_area < 500000.0
    ORDER BY sml DESC;"""

    data = (location['lon'], location['lat'], name, distance)
    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return dict(res) if res else {}


def get_osm_polygon_feature_from_name_with_buffer(name, location, distance=50):
    connection, cursor = connect_to_db("osm", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH point_buffer AS (
	     SELECT ST_Buffer(ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s), 4326),3857), %s) as buffer, %s as name
    )

    SELECT p.osm_id, p.name, pt.name, word_similarity(pt.name, p.name) as sml, 
           ST_Transform(way, 4326) as poly, 
           st_area(st_intersection(pt.buffer, p.way)) / st_area(pt.buffer) as intersect_area
    FROM planet_osm_polygon p, point_buffer pt
    WHERE (p.name %% pt.name)
          AND ST_Intersects(pt.buffer, p.way)
          AND p.admin_level IS NULL AND p.way_area < 500000.0
    ORDER BY sml DESC;"""

    data = (location['lon'], location['lat'], distance, name)
    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return dict(res) if res else {}


def get_osm_polygon_feature_from_housename(name, location, distance=50):
    connection, cursor = connect_to_db("osm", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH venue AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as point, %s as name
    )

    SELECT p.osm_id, p."addr:housename", v.name, word_similarity(v.name, p."addr:housename") as sml, 
           ST_Transform(way, 4326) as poly
    FROM planet_osm_polygon p, venue v
    WHERE (p."addr:housename" %% v.name)
          AND ST_DWITHIN(p.way, v.point, %s)
          AND p.admin_level IS NULL AND p.way_area < 500000.0
    ORDER BY sml DESC;"""

    data = (location['lon'], location['lat'], name, distance)
    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return dict(res) if res else {}


def get_osm_polygon_feature_from_housename_with_buffer(name, location, distance=50):
    connection, cursor = connect_to_db("osm", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH point_buffer AS (
	     SELECT ST_Buffer(ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s), 4326),3857), %s) as buffer, %s as name
    )

    SELECT p.osm_id, p."addr:housename", pt.name, word_similarity(pt.name, p."addr:housename") as sml, 
           ST_Transform(way, 4326) as poly, 
           st_area(st_intersection(pt.buffer, p.way)) / st_area(pt.buffer) as intersect_area
    FROM planet_osm_polygon p, point_buffer pt
    WHERE (p."addr:housename" %% pt.name)
          AND ST_Intersects(pt.buffer, p.way)
          AND p.admin_level IS NULL AND p.way_area < 500000.0
    ORDER BY sml DESC;"""

    data = (location['lon'], location['lat'], distance, name)
    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return dict(res) if res else {}


def get_venues_from_foursquare():
    connection, cursor = connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
    SELECT name, longitude as lon, latitude as lat, venue_id
    FROM venues
    ORDER BY nb_checkins DESC;"""
    cursor.execute(query_string)
    return [dict(res) for res in cursor]


def update_venue_polygon_in_foursquare(venue_id, poly):
    connection, cursor = connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """UPDATE venues SET poly = %s WHERE venue_id = %s"""
    data = (poly, venue_id)
    cursor.execute(query_string, data)
    connection.commit()


def process_all_foursquare_venues():
    all_venues = get_venues_from_foursquare()
    print("processing %s venues" % len(all_venues))
    f = open("output-process-all-foursquare-venues-buffer.txt", 'w')
    count = 0
    for venue in all_venues:
        venue_id = venue['venue_id']
        venue_name = venue['name']

        osm_id = ""
        venue_location = {'lat': venue['lat'], 'lon': venue['lon']}
        res = get_osm_polygon_feature_from_name_with_buffer(venue['name'], venue_location, 250)
        if not res or res['sml'] < 0.45:
            res = get_osm_polygon_feature_from_housename_with_buffer(venue['name'], venue_location, 250)

        if res and res['poly'] and res['sml'] >= 0.45:
            osm_id = res['osm_id']
            poly = res['poly']
            print_progress("[%s / %s] %s (%s)" % (count, len(all_venues), venue_name, venue_id))
            update_venue_polygon_in_foursquare(venue_id, poly)

        if osm_id != "":
            f.write("UPDATE\t%s\t%s\t%s\n" % (venue_id, venue_name, osm_id))
        else:
            f.write("FAILED\t%s\t%s\t%s\n" % (venue_id, venue_name, osm_id))

        count += 1

    print()
    f.close()


if __name__ == '__main__':
    base = sys.argv[0]
    if len(sys.argv) == 1:
        print("Error - please specify an argument")
        sys.exit(0)

    arg = sys.argv[1]
    if arg == 'all':
        process_all_foursquare_venues()
