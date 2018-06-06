import os
import sys
import time
import shlex
import re
import psycopg2.extras

import utils


def remove_xml_tags(obj):
    if obj[0] == '<' and obj[-1] == '>':
        return obj[1:-1]
    else:
        return obj


def get_name_from_uri(obj_uri):
    m = re.match(place_uri_pattern, obj_uri.replace('%3F', ''))
    try:
        return m.group(1).replace("_", " ")
    except AttributeError as e:
        print("AttributeError for {}".format(obj_uri))

    return ""


def print_progress(s):
    sys.stdout.write("\r\x1b[K" + s)
    sys.stdout.flush()


def split(s):
    lex = shlex.shlex(s)
    lex.quotes = '"'
    lex.whitespace_split = True
    lex.commenters = ''
    return list(lex)


DB_HOSTNAME = 'colossus07'
place_uri_pattern = r".*\b\/(?:\w+\:)?([^\/:]+)\>$"
point_predicate = '<http://www.georss.org/georss/point>'
lat_predicate = '<http://www.w3.org/2003/01/geo/wgs84_pos#lat>'
lon_predicate = '<http://www.w3.org/2003/01/geo/wgs84_pos#long>'
type_predicate = '<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>'
subject_predicate = '<http://purl.org/dc/terms/subject>'


def load_ttl(filepath, d):
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip().replace("^^", " ").replace("\"", "")
            fields = line.strip().split(" ")
            subject = fields[0]
            predicate = fields[1]
            obj = fields[2]
            if subject not in d:
                d[subject] = {}
            if predicate not in d[subject]:
                d[subject][predicate] = []
            d[subject][predicate].append(obj)
    print("done loading {} with {} objects".format(filepath, len(d)))


def save_nodes_to_db(geo_mapped_instances, instances):
    connection, cursor = utils.connect_to_db("dbpedia")

    date_added = 2016
    count = 0
    for node in geo_mapped_instances.keys():
        if lon_predicate not in geo_mapped_instances[node] or lat_predicate not in geo_mapped_instances[node]:
            print('Could not insert {} into database'.format(node))
            continue

        place_name = get_name_from_uri(node)
        place_uri = node

        lon = float(geo_mapped_instances[node][lon_predicate][0])
        lat = float(geo_mapped_instances[node][lat_predicate][0])
        location_point = "POINT({} {})".format(lon, lat)
        place_type = ""
        if node in instances:
            if type_predicate in instances[node]:
                place_type = instances[node][type_predicate][0]

        query_string = """INSERT INTO places 
        (date_added, uri, name, type_uri, longitude, latitude, geom)
        VALUES (%s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
        ON CONFLICT DO NOTHING;"""
        data = (date_added, place_uri, place_name, place_type, lon, lat, location_point)

        cursor.execute(query_string, data)

        count += 1
        if count % 100 == 0:
            print_progress("Done %.2f" % (100.0 * count / len(geo_mapped_instances)))

    connection.commit()
    print()


def get_places(location, distance=200, limit=5):
    connection, cursor = utils.connect_to_db("dbpedia", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH place AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords
    )
    SELECT name, uri, longitude, latitude,
           ST_Distance(p.coords, ST_TRANSFORM(geom, 3857)) AS distance
    FROM places, place p
    WHERE latitude <> -90 AND longitude <> 0 AND 
          ST_DWithin(ST_TRANSFORM(geom, 3857), p.coords, %s)      
    ORDER BY distance ASC
    LIMIT %s;"""
    data = (location['lon'], location['lat'], distance, limit)

    cursor.execute(query_string, data)
    records = cursor.fetchall()

    places = []
    for rec in records:
        loc = {"name": rec['place_name'],
               "color": "#261b7c",
               "id": rec['place_uri'],
               "distance": rec["distance"],
               "location": {
                   "lon": rec['longitude'],
                   "lat": rec['latitude']
                 }
               }
        places.append(loc)

    return places


def get_place_with_name(location, query, distance=200):
    connection, cursor = utils.connect_to_db("dbpedia", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH place AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as coords, %s as query
    )
    SELECT name, uri, place_id, longitude, latitude, type_uri,
           word_similarity(name, p.query) as sml, 
           ST_Distance(p.coords, ST_TRANSFORM(geom, 3857)) as distance
    FROM places, place p
    WHERE p.query <%% name 
          AND ST_DWITHIN(ST_TRANSFORM(geom, 3857), p.coords, %s)
    ORDER BY sml DESC, distance DESC
    LIMIT 1;"""
    data = (location['lon'], location['lat'], query, distance)

    cursor.execute(query_string, data)
    rec = cursor.fetchone()

    if not rec:
        return None

    loc = {"name": rec['name'],
           "id": rec['place_id'],
           "uri": rec['uri'],
           "distance": rec['distance'],
           "sml": rec['sml'],
           "type": rec['type_uri'],
           "location": {
               "lon": rec['longitude'],
               "lat": rec['latitude']
             }
           }

    return loc


def get_place_personal_information_ids(place_id):
    connection, cursor = utils.connect_to_db("dbpedia", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    SELECT name, frequency, total_count, type_uris 
    FROM 
    (
      SELECT unnest(personal_information) as id
      FROM places
      WHERE place_id = %s
      GROUP BY id
    ) p INNER JOIN personal_information ON pi_id = id
    WHERE discard IS FALSE
    ORDER BY frequency DESC;"""
    data = (place_id,)

    cursor.execute(query_string, data)
    records = cursor.fetchall()
    return [dict(rec) for rec in records]


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print("Error - please specify a path for the dbpedia files")
        sys.exit(0)

    path = sys.argv[1]

    ontology_path = path + "dbpedia_ontology_2016.nt"

    instance_types_path = path + "instance_types_en.ttl"  # gives the type of the instance (as defined in http://wiki.dbpedia.org/services-resources/ontology)
    instance_categories_path = path + "article_categories_en.ttl"  # gives the categories of the instance (subject)

    geo_coordinate_path = path + "geo_coordinates_en.tql"  # Get the categories of the geo-mapped objects
    geo_coordinate_mappingbased_path = path + "geo_coordinates_mappingbased_en.tql"

    # ontology = {}
    # load_ttl(ontology_path, ontology)

    instances = {}
    load_ttl(instance_types_path, instances)
    # load_ttl(instance_categories_path, instances)

    geo_mapped_instances = {}
    load_ttl(geo_coordinate_path, geo_mapped_instances)
    load_ttl(geo_coordinate_mappingbased_path, geo_mapped_instances)

    save_nodes_to_db(geo_mapped_instances, instances)
    print("saved nodes into database")