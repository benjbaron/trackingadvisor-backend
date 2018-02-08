import sys
import os
import re
import json
import time
import math
import geocoder
import geojson
import numpy
import random
import datetime
from sklearn.neighbors import DistanceMetric
import psycopg2
import psycopg2.extras

NB_MAX_CONN = 25
DB_HOSTNAME = "colossus07"
if "DB_HOSTNAME" in os.environ:
    DB_HOSTNAME = os.environ.get("DB_HOSTNAME")


UCL_COLORS = [
    ("Dark Green", "#555025"),
    ("Dark Red", "#651D32"),
    ("Dark Purple", "#4B384C"),
    ("Dark Blue", "#003D4C"),
    ("Dark Brown", "#4E3629"),
    ("Mid Green", "#8F993E"),
    ("Mid Red", "#93272C"),
    ("Mid Purple", "#500778"),
    ("Mid Blue", "#002855"),
    ("Blue", "#24509A")
]

UCL_COLOR_HOME = ("Orange", "#EA7600")


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
            time.sleep(random.uniform(0.01, nb_req / 10.0))
        else:
            return connection, cursor

    print("Error connecting the database")
    sys.exit(0)


def pick_place_color(place_name):
    if place_name.lower() == 'home':
        return UCL_COLOR_HOME[1]

    idx = len(place_name) % len(UCL_COLORS)
    return UCL_COLORS[idx][1]


def timestamp_from_string(s):
    return time.mktime(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").timetuple())


def datetime_from_timestamp(ts):
    return datetime.datetime.fromtimestamp(ts)


def decode_personal_information(info):
    pattern = r"(\w+)(?:\[([a-zA-Z;_]*)\])?"
    m = re.search(pattern, info)
    cat, keys = m.groups()
    return cat, (keys.split(';') if keys else [])


def print_progress(s):
    sys.stdout.write("\r\x1b[K" + s)
    sys.stdout.flush()


def compute_medoid(raw_points):
    points = numpy.radians([[p[0], p[1]] for p in raw_points])
    d = DistanceMetric.get_metric('haversine')
    dists = d.pairwise(points)
    index = numpy.argmin(dists.sum(axis=0))
    return index


def compute_diameter(raw_points):
    points = numpy.radians([[p[0], p[1]] for p in raw_points])
    d = DistanceMetric.get_metric('haversine')
    dists = d.pairwise(points).flatten()
    return dists[numpy.argmax(dists)] * 6372795


def monitor_map_progress(map_result, d, total, title="Progress: "):
    while True:
        if map_result.ready():
            break
        else:
            size = sum(1 for k in d.keys() if d[k] == 'done')
            s = title + "%.2f done" % (100 * size / total)
            # s += " [%s]" % (", ".join([str(k) for k in d.keys() if d[k] == 'running']))
            print_progress(s)
            time.sleep(0.5)


def get_address(location):
    g = None
    count = 0
    while (not g or not g.city) and count < 10:
        g = geocoder.google([location['lat'], location['lon']], method='reverse')
        time.sleep(0.01)
        count += 1

    street = None
    if g.housenumber and g.street:
        street = "{} {}".format(g.housenumber, g.street)
    elif g.street:
        street = "{}".format(g.street)
    return street, g.city


def get_boundaries_from_location(location):
    g = 0
    count = 0
    while (not g or not g.json or not'raw' in g.json) and count < 10:
        g = geocoder.google(location)
        time.sleep(0.01)
        count += 1

    if count == g.json:
        return {}, {}

    return g.json['raw']['geometry']['bounds'], {'lat': g.json['lat'], 'lon': g.json['lng']}


# Semi-axes of WGS-84 geoidal reference
WGS84_a = 6378137.0  # Major semiaxis [m]
WGS84_b = 6356752.3  # Minor semiaxis [m]


def deg2rad(degrees):
    # degrees to radians
    return math.pi*float(degrees)/180.0


def rad2deg(radians):
    # radians to degrees
    return 180.0*float(radians)/math.pi


# Earth radius at a given latitude, according to the WGS-84 ellipsoid [m]
def WGS84EarthRadius(lat):
    # http://en.wikipedia.org/wiki/Earth_radius
    An = WGS84_a*WGS84_a * math.cos(lat)
    Bn = WGS84_b*WGS84_b * math.sin(lat)
    Ad = WGS84_a * math.cos(lat)
    Bd = WGS84_b * math.sin(lat)
    return math.sqrt( (An*An + Bn*Bn)/(Ad*Ad + Bd*Bd) )


# Bounding box surrounding the point at given coordinates,
# assuming local approximation of Earth surface as a sphere
# of radius given by WGS84
def bounding_box(latitudeInDegrees, longitudeInDegrees, halfSideInKm):
    lat = deg2rad(latitudeInDegrees)
    lon = deg2rad(longitudeInDegrees)
    halfSide = 1000 * halfSideInKm

    # Radius of Earth at given latitude
    radius = WGS84EarthRadius(lat)
    # Radius of the parallel at given latitude
    pradius = radius*math.cos(lat)

    latMin = lat - halfSide/radius
    latMax = lat + halfSide/radius
    lonMin = lon - halfSide/pradius
    lonMax = lon + halfSide/pradius

    boundary = {'southwest': {'lng': rad2deg(lonMin),'lat': rad2deg(latMin) },
                'northeast': {'lng': rad2deg(lonMax), 'lat': rad2deg(latMax) } }

    return boundary


def calculate_height_width(boundary):
    height = haversine(boundary['southwest']['lng'],
                       boundary['northeast']['lat'],
                       boundary['northeast']['lng'],
                       boundary['northeast']['lat'])
    width  = haversine(boundary['southwest']['lng'],
                       boundary['northeast']['lat'],
                       boundary['southwest']['lng'],
                       boundary['southwest']['lat'])
    return height, width


def divide_cells(boundary):
    """ Divides the boundary into four cells """
    height, width = calculate_height_width(boundary)

    cell1 = get_cell(boundary['southwest'], height/2.0, width/2.0)
    cell2 = {'southwest': {'lat': cell1['southwest']['lat'], 'lng': cell1['northeast']['lng']},
    		 'northeast': {'lat': cell1['northeast']['lat'], 'lng': boundary['northeast']['lng']}}
    cell3 = {'southwest': cell1['northeast'],
    		 'northeast': boundary['northeast']}
    cell4 = {'southwest': {'lat': cell1['northeast']['lat'], 'lng': cell1['southwest']['lng']},
    		 'northeast': {'lat': boundary['northeast']['lat'], 'lng': cell1['northeast']['lng']}}

    return [cell1, cell2, cell3, cell4]


def get_cell(southwest, dn, de):
    """ see http://stackoverflow.com/questions/7222382/get-lat-long-given-current-point-distance-and-bearing """
    R = 6378137  # Radius of the Earth

    lat1 = math.radians(southwest['lat'])  # Current lat point converted to radians
    lon1 = math.radians(southwest['lng'])  # Current long point converted to radians

    brng = math.radians(0)  # Bearing is 0 degrees converted to radians.
    lat2 = math.asin( math.sin(lat1)*math.cos(de/R) +
           math.cos(lat1)*math.sin(de/R)*math.cos(brng))

    brng = math.radians(90)  # Bearing is 90 degrees converted to radians.
    lon2 = lon1 + math.atan2(math.sin(brng)*math.sin(dn/R)*math.cos(lat1),
                  math.cos(dn/R)-math.sin(lat1)*math.sin(lat2))

    lat2 = math.degrees(lat2)
    lon2 = math.degrees(lon2)

    northeast = {'lat': lat2, 'lng': lon2}
    return {'southwest': southwest, 'northeast': northeast}


def haversine(lon1, lat1, lon2, lat2):
    """ Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6378137  # Radius of earth in meters
    return c * r


def get_boundary_cells(boundary, cell_size):
    """
    Returns the list of cells to examine of 'cell_size' at a location
    """
    # get the boundaries of the location ; 'cell_size' is in meters
    boundaries = []
    height,width = calculate_height_width(boundary)
    nrof_y_cells = max(1, int(math.ceil(height / cell_size)))
    nrof_x_cells = max(1, int(math.ceil(width  / cell_size)))

    inc_width = 0.0
    for i in range(nrof_x_cells):
        inc_width += cell_size
        inc_height = 0.0
        for j in range(nrof_y_cells):
            inc_height += cell_size
            if inc_width > width:
                x_size = inc_width-width
            else:
                x_size = cell_size
            if inc_height > height:
                y_size = inc_height-height
            else:
                y_size = cell_size
            cell = get_cell(boundary['southwest'], i*cell_size, j*cell_size)
            boundaries.append(get_cell(cell['northeast'], x_size, y_size))

    return boundaries


def wkt_to_geojson(wkt):
    g1 = shapely.wkt.loads(wkt)
    g2 = geojson.Feature(geometry=g1, properties={})
    return g2.geometry


def boundary_to_geojson_polygon(boundary):
    feature = {
      "type": "Feature",
      "properties": {},
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [
              boundary['southwest']['lng'],
              boundary['northeast']['lat']
            ],
            [
              boundary['northeast']['lng'],
              boundary['northeast']['lat']
            ],
            [
              boundary['northeast']['lng'],
              boundary['southwest']['lat']
            ],
            [
              boundary['southwest']['lng'],
              boundary['southwest']['lat']
            ],
            [
              boundary['southwest']['lng'],
              boundary['northeast']['lat']
            ]
          ]
        ]
      }
    }

    return json.dumps(feature)


def boundary_to_wkt_polygon(boundary):
    return 'POLYGON(({} {}, {} {}, {} {}, {} {}, {} {}))'.format(
        boundary['southwest']['lng'],
        boundary['northeast']['lat'],
        boundary['northeast']['lng'],
        boundary['northeast']['lat'],
        boundary['northeast']['lng'],
        boundary['southwest']['lat'],
        boundary['southwest']['lng'],
        boundary['southwest']['lat'],
        boundary['southwest']['lng'],
        boundary['northeast']['lat']
    )


if __name__ == '__main__':
    lon = -0.134602
    lat = 51.524651
    bounding_box = bounding_box(lat, lon, 0.5)
    print(bounding_box)
    for cell in divide_cells(bounding_box):
        print(boundary_to_wkt_polygon(cell))
