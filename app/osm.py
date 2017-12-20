import os
import geojson
import shapely.wkt
import psycopg2
import psycopg2.extras
from collections import OrderedDict

DB_HOSTNAME = "localhost"
if "DB_HOSTNAME" in os.environ:
    DB_HOSTNAME = os.environ.get("DB_HOSTNAME")


def wkt_to_geojson(wkt):
    g1 = shapely.wkt.loads(wkt)
    g2 = geojson.Feature(geometry=g1, properties={})
    return g2.geometry


def connect_to_database():    
    conn_string = "host='localhost' dbname='osm' user='postgres' password='postgres'"
    conn = psycopg2.connect(conn_string)
    return conn.cursor(cursor_factory=psycopg2.extras.DictCursor)


def query_pois(location, distance=200):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="osm", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    lat = location['lat']
    lon = location['lon']
    query_string = """
    WITH point AS (
	     SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s), 4326),3857) as pt
    )
    SELECT 
            ST_Y(ST_Transform(point.way, 4326)) AS lat,
            ST_X(ST_Transform(point.way, 4326)) AS lon, 
            poly.name as place, 
            point.name as location,
            ST_Distance(pt.pt, point.way) AS distance,
            point.tags as point_tags,
            poly.tags as poly_tags,
            point.osm_id as point_id,
            poly.osm_id as poly_id,
            poly.admin_level as admin_level,
            poly.way_area as area
        FROM point AS pt, planet_osm_point point LEFT JOIN planet_osm_polygon poly 
        ON st_intersects(point.way, poly.way) 
        WHERE ST_DWITHIN(point.way, pt.pt,4326),3857), %s)
              AND point.name IS NOT NULL AND poly.name IS NOT NULL
        ORDER BY distance ASC;
    """
    data = (lon, lat, distance)
    cursor.execute(query_string, data)
    records = cursor.fetchall()
    return records


def get_polygons(location, distance=50):
    lat = location['lat']
    lon = location['lon']

    connection = psycopg2.connect(host=DB_HOSTNAME, database="osm", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
    query_string = """
    WITH point_buffer AS (
	     SELECT ST_Buffer(ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s), 4326),3857), %s) as buffer
    )
    SELECT poly.name,  poly."addr:housename" as housename, poly.osm_id as id, poly.tags, poly.building, poly.way_area as area, 
           st_area(st_intersection(pt.buffer, poly.way)) / st_area(pt.buffer) as intersect_area
    FROM planet_osm_polygon poly, point_buffer pt
    WHERE (name is not null OR "addr:housename" IS NOT NULL) AND
          poly.admin_level IS NULL AND 
          poly.way_area < 500000.0 AND
          ST_Intersects(pt.buffer, poly.way)
    ORDER BY intersect_area DESC;
    """
    data = (lon, lat, distance)

    cursor.execute(query_string, data)
    records = cursor.fetchall()

    places = []
    for rec in records:
        if rec['intersect_area'] > 0.01:
            geom, center = get_wkt_polygon(rec['id'])
            places.append({
                "name": rec['name'] if rec['name'] else rec['housename'],
                "color": "#9ED382",
                "category": rec['tags'],
                'id': rec['id'],
                'area': rec['area'],
                'building': rec['building'],
                'intersect_area': rec['intersect_area'],
                'geom': geom,
                'center': center,
                'color': "#503991"
            })

    return places


def get_wkt_polygon(poly_id):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="osm", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """SELECT ST_AsText(ST_TRANSFORM(way, 4326)) as geom, ST_AsText(ST_TRANSFORM(ST_Centroid(way), 4326)) as center
        FROM planet_osm_polygon poly
        WHERE osm_id = %s;"""

    cursor.execute(query_string, (poly_id,))
    res = cursor.fetchone()
    geom = res['geom']
    center = res['center']
    return wkt_to_geojson(geom), wkt_to_geojson(center)


def get_address_with_number(location):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="osm", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
    WITH point AS (
        SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as pt
    )
    SELECT poly."addr:housenumber", poly.tags, ST_Distance(ST_Centroid(poly.way), pt.pt) AS distance
    FROM planet_osm_polygon poly, point pt
    WHERE ST_DWITHIN(poly.way, pt.pt, %s) AND poly."addr:housenumber" IS NOT NULL
    ORDER BY distance ASC;"""

    cursor.execute(query_string, (location['lon'], location['lat'], 25))
    res = cursor.fetchone()
    addr_number = res['addr:housenumber']
    tags = res['tags'].split(',')
    print(tags)
    street_name = ""
    for tag in tags:
        k, v = tag.replace('"', '').split("=>")
        print(k, v)
        if k == 'addr:street':
            street_name = v
    return "{} {}".format(addr_number, street_name)


def get_closest_polygon(location):
    print("get closest polygon from location {}".format(location))
    connection = psycopg2.connect(host=DB_HOSTNAME, database="osm", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
       WITH point AS (
           SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as pt
       )
       SELECT osm_id, poly."addr:housenumber", poly.tags, ST_Distance(ST_Centroid(poly.way), pt.pt) AS distance
       FROM planet_osm_polygon poly, point pt
       WHERE ST_DWITHIN(poly.way, pt.pt, %s) AND poly.building IS NOT NULL
       ORDER BY distance ASC;"""

    cursor.execute(query_string, (location['lon'], location['lat'], 25))
    res = cursor.fetchone()
    return res['osm_id'] if res else ''


def get_places(location, distance, limit):
    print(location)
    places = OrderedDict()
    records = query_pois(location, distance)

    print("retrieved {} records".format(len(records)))
    for rec in records:
        if rec['point_id'] not in places:
            places[rec['point_id']] = {
                'location': {'lon': rec['lon'], 'lat': rec['lat']},
                'places': [],
                'name': rec['location'],
                'tags': rec['point_tags'],
                'id': rec['point_id'],
                'distance': rec['distance']
            }
        # Add the place
        if rec['place'] and not rec['admin_level'] and rec['area'] < 500000.0:
            places[rec['point_id']]['places'].append({
                'name': rec['place'],
                'tags': rec['poly_tags'],
                'id': rec['poly_id'],
                'admin_level': rec['admin_level'],
                'area': rec['area']
            })

    print("retrieved {} places".format(len(places)))
    res = {'places': {}, 'polygons': {}}
    for i in range(0, min(limit, len(places))):
        place = list(places.values())[i]
        name = place['name']
        res['places'][place['id']] = {
            "name": name,
        	"color": "#9ED382",
        	"category": place['tags'],
            "location": place['location'],
            "places": [p['id'] for p in place['places']]
        }
        for p in place['places']:
            poly_id = p['id']
            if poly_id in res['polygons']:
                continue

            geom, center = get_wkt_polygon(poly_id)
            res['polygons'][poly_id] = p
            res['polygons'][poly_id]['geom'] = geom
            res['polygons'][poly_id]['center'] = center
            res['polygons'][poly_id]['color'] = "#503991"

    return res


def get_osm_point_feature_from_name(name, location, distance=50):
    print("getting polygon from name {} within {} of {}".format(name, location, distance))

    connection = psycopg2.connect(host=DB_HOSTNAME, database="osm", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
    WITH venue AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as point, %s as name
    )
    SELECT p.osm_id, p.name, word_similarity(v.name, p.name) as sml
    FROM planet_osm_point p, venue v
    WHERE ST_DWITHIN(p.way, v.point, %s) AND p.name IS NOT NULL AND v.name <%% p.name
    ORDER BY sml DESC;"""

    data = (location['lon'], location['lat'], name, distance)
    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return res['osm_id'] if res else ''


def get_osm_polygon_feature_from_name(name, location, distance=50):
    print("getting polygon from name {} within {} of {}".format(name, location, distance))

    connection = psycopg2.connect(host=DB_HOSTNAME, database="osm", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query_string = """
    WITH venue AS (
      SELECT ST_TRANSFORM(ST_SETSRID(ST_MAKEPOINT(%s, %s),4326),3857) as point, %s as name
    )
    SELECT p.osm_id, p.name, word_similarity(v.name, p.name) as sml
    FROM planet_osm_polygon p, venue v
    WHERE ST_DWITHIN(p.way, v.point, %s) AND p.name IS NOT NULL AND v.name <%% p.name
          AND p.admin_level IS NULL AND p.way_area < 500000.0
    ORDER BY sml DESC;"""

    data = (location['lon'], location['lat'], name, distance)
    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return res['osm_id'] if res else ''


if __name__ == '__main__':
    # lon = -0.134602 ; lat = 51.524651
    location = {'lat': 51.5247377069669, 'lon': -0.123987639372744}
    # print(get_polygons(location, 50))
    # print(get_address_with_number(location))

    print(get_osm_point_feature_from_name("Waitrose", location, 50))
    # places = get_places(location, 200, 5)
    # print(places)
