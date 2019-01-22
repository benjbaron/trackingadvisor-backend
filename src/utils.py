import sys
import os
import re
import json
import time
import math
import string
import geocoder
import geojson
import numpy
import random
import datetime
import calendar
from sklearn.neighbors import DistanceMetric
import psycopg2
import psycopg2.extras
from pymongo import MongoClient

from keys import MAPBOX_TOKEN


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
ARTICLES = {'a', 'an', 'of', 'the', 'is', 'and', 'at', 'in', 'on', 'yes'}


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def connect_to_db(database_name, cursor_type=None):
    nb_req = 0
    while nb_req < NB_MAX_CONN:
        try:
            connection = psycopg2.connect(host=DB_HOSTNAME, database=database_name, user="postgres", password="G2j!3IqdD%EX")
            if cursor_type:
                cursor = connection.cursor(cursor_factory=cursor_type)
            else:
                cursor = connection.cursor()
        except psycopg2.Error as e:
            nb_req += 1
            time.sleep(random.uniform(0.01, 0.1))
        else:
            return connection, cursor

    print("Error connecting the PostgreSQL database")
    sys.exit(0)


def connect_to_mongo():
    nb_req = 0
    while nb_req < NB_MAX_CONN:
        try:
            client = MongoClient(DB_HOSTNAME, 27017)
        except:
            nb_req += 1
            time.sleep(random.uniform(0.1, 1.0))
        else:
            return client

    print("Error connecting the Mongo database")
    sys.exit(0)


def title_except(s, exceptions=ARTICLES):
    word_list = re.split(" ", s)       # re.split behaves as expected
    final = [word_list[0].capitalize()]
    for word in word_list[1:]:
        final.append(word if word in exceptions else word.capitalize())
    return " ".join(final)


def pick_place_color(place_name):
    if place_name.lower() == 'home':
        return UCL_COLOR_HOME[1]

    idx = len(place_name) % len(UCL_COLORS)
    return UCL_COLORS[idx][1]


def current_timestamp():
    return int(time.mktime(time.gmtime()))


def is_weekend(day):
    weekdays = [1, 1, 1, 1, 1, 0, 0]
    day_dt = day_string_to_dt(day)
    idx = day_dt.weekday()
    return weekdays[idx] == 0


def time_diff_seconds(time_a, time_b):
    today = datetime.date.today()
    return (datetime.datetime.combine(today, time_b) - datetime.datetime.combine(today, time_a)).seconds


def seconds_in_overlapping_ranges_hour(start_t, end_t, h_start, h_end):
    if h_end < h_start:
        return 0

    if end_t.hour >= h_start and start_t.hour <= h_end:
        start = max(start_t, datetime.time(h_start, 0, 0))
        end = min(end_t, datetime.time(h_end, 59, 59))
        return time_diff_seconds(start, end)

    return 0


def seconds_in_hour_range(start, end, intervals):
    start_t = datetime_from_timestamp(start).time()
    end_t = datetime_from_timestamp(end).time()

    res = 0
    for i in range(len(intervals)):
        res += seconds_in_overlapping_ranges_hour(start_t, end_t, intervals[i][0], intervals[i][1])

    return res


def timestamp_to_day_str(ts):
    d = datetime_from_timestamp(ts)
    return d.strftime("%Y-%m-%d")


def today_string():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def timestamp_from_string(s):
    if s == '':
        return 0
    if '.' in s:
        return calendar.timegm(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f %z").timetuple())
    return calendar.timegm(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").timetuple())


def timestamp_utc_from_string(s):
    if s == '':
        return 0
    if '.' in s:
        return calendar.timegm(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f %z").utctimetuple())
    return calendar.timegm(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z").utctimetuple())


def datetime_from_timestamp(ts):
    return datetime.datetime.utcfromtimestamp(ts)


def timestamp_from_datetime(dt):
    return int(time.mktime(dt.utctimetuple()))


def day_string_to_dt(day):
    return datetime.datetime.strptime(day, "%Y-%m-%d")


def hm(ts):
    dt = datetime.datetime.utcfromtimestamp(ts)
    return "%02d:%02d" % (dt.hour, dt.minute)


def day_hm(ts):
    dt = datetime.datetime.utcfromtimestamp(ts)
    return "%04d-%02d-%02d %02d:%02d" % (dt.year, dt.month, dt.day, dt.hour, dt.minute)


def previous_day(day):
    d = datetime.datetime.strptime(day, "%Y-%m-%d").date()
    day_before = d + datetime.timedelta(days=-1)
    return day_before.strftime("%Y-%m-%d")


def previous_day_ts(ts):
    d = datetime_from_timestamp(ts)
    day_before = d + datetime.timedelta(days=-1)
    return timestamp_from_datetime(day_before)


def next_day(day):
    d = datetime.datetime.strptime(day, "%Y-%m-%d").date()
    day_after = d + datetime.timedelta(days=1)
    return day_after.strftime("%Y-%m-%d")


def next_day_ts(ts):
    d = datetime_from_timestamp(ts)
    day_after = d + datetime.timedelta(days=1)
    return timestamp_from_datetime(day_after)


def start_of_day(ts):
    today = datetime_from_timestamp(ts)
    today_beginning = datetime.datetime(today.year, today.month, today.day, 0, 0, 0, 0)
    return int(time.mktime(today_beginning.utctimetuple()))


def end_of_day(ts):
    today = datetime_from_timestamp(ts)
    today_end = datetime.datetime(today.year, today.month, today.day, 23, 59, 59, 999)
    return int(time.mktime(today_end.utctimetuple()))


def start_of_day_str(day):
    d = datetime.datetime.strptime(day, "%Y-%m-%d").date()
    day_beginning = datetime.datetime(d.year, d.month, d.day, 0, 0, 0, 0)
    return int(time.mktime(day_beginning.utctimetuple()))


def end_of_day_str(day):
    d = datetime.datetime.strptime(day, "%Y-%m-%d").date()
    day_end = datetime.datetime(d.year, d.month, d.day, 23, 59, 59, 999)
    return int(time.mktime(day_end.utctimetuple()))


def today_timestamp_at_time(t):
    d = datetime.datetime.now().date()
    h, m = [int(e) for e in t.split(":")]
    day_time = datetime.datetime(d.year, d.month, d.day, h, m, 0, 0)
    return int(time.mktime(day_time.utctimetuple()))


def seconds_since_start_of_day(ts):
    sod = start_of_day(ts)
    return ts - sod


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


def compute_average_inter_distance(raw_points):
    points = numpy.radians([[p[0], p[1]] for p in raw_points])
    d = DistanceMetric.get_metric('haversine')
    dists = [d.pairwise([p1, p2])[1][0] for p1,p2 in zip(points[1:], points[:-1])]
    return numpy.average(dists) * 6372795


def compute_average_speeds(raw_points):
    points = numpy.radians([[p[0], p[1]] for p in raw_points])
    d = DistanceMetric.get_metric('haversine')
    dists = numpy.array([d.pairwise([p1, p2])[1][0] for p1,p2 in zip(points[1:], points[:-1])])
    times = numpy.array([p1[2] - p2[2] for p1,p2 in zip(raw_points[1:], raw_points[:-1])])
    speeds = dists * 6372795 / times
    return numpy.average(speeds)


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


def create_random_point(x0, y0, distance):
    """ Utility method for the generation of random points within a distance. """
    r = distance / 111300
    u = numpy.random.uniform(0, 1)
    v = numpy.random.uniform(0, 1)
    w = r * numpy.sqrt(u)
    t = 2 * numpy.pi * v
    x = w * numpy.cos(t)
    x1 = x / numpy.cos(y0)
    y = w * numpy.sin(t)
    return [x0+x1, y0+y]


def get_address(location):
    g = None
    count = 0
    while (not g or not g.city) and count < 10:
        g = geocoder.mapbox([location['lat'], location['lon']], method='reverse', key=MAPBOX_TOKEN)
        time.sleep(0.01)
        count += 1

    housenumber = g.housenumber
    street = g.raw.get('text', '')
    address = ""
    if housenumber and street:
        address = "{} {}".format(housenumber, street)
    elif street:
        address = "{}".format(street)
    return address, g.city


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


def generate_qr_code(url, logo_path, output_file):
    import pyqrcode
    from lxml import etree
    
    block_size = 10
    circle_radius = block_size * 4

    def distance(p0, p1):
        return math.sqrt((p0[0] - p1[0]) ** 2 + (p0[1] - p1[1]) ** 2)

    def generateQRImageForUrl(url):
        qr_image = pyqrcode.MakeQRImage(url, errorCorrectLevel=pyqrcode.QRErrorCorrectLevel.H, block_in_pixels=1,
                                        border_in_blocks=0)
        return qr_image

    def getSVGFileContent(filename):
        """
        root may be the svg element itself, so search from tree

        solution for multiple (or no) namespaces from
        http://stackoverflow.com/a/14552559/493161
        """
        document = etree.parse(filename)
        svg = document.xpath('//*[local-name()="svg"]')[0]
        return svg

    def touchesBounds(center, x, y, radius, block_size):
        scaled_center = center / block_size
        dis = distance((scaled_center, scaled_center), (x, y))
        rad = radius / block_size
        return dis <= rad + 1

    im = generateQRImageForUrl(url)

    imageSize = str(im.size[0] * block_size)

    # create an SVG XML element (see the SVG specification for attribute details)
    doc = etree.Element('svg', width=imageSize, height=imageSize, version='1.1', xmlns='http://www.w3.org/2000/svg')

    pix = im.load()

    center = im.size[0] * block_size / 2

    for xPos in range(0, im.size[0]):
        for yPos in range(0, im.size[1]):

            color = pix[xPos, yPos]
            if color == (0, 0, 0, 255):

                withinBounds = not touchesBounds(center, xPos, yPos, circle_radius, block_size)

                if withinBounds:
                    etree.SubElement(doc, 'rect', x=str(xPos * block_size), y=str(yPos * block_size), width='10',
                                     height='10', fill='black')

    logo = getSVGFileContent(logo_path)

    test = str(logo.get("viewBox"))
    array = []

    if test != "None":
        array = test.split(" ")
        width = float(array[2])
        height = float(array[3])
    else:
        width = float(str(logo.get("width")).replace("px", ""))
        height = float(str(logo.get("height")).replace("px", ""))

    scale = circle_radius * 2.0 / width

    scale_str = "scale(" + str(scale) + ")"

    xTrans = ((im.size[0] * block_size) - (width * scale)) / 2.0
    yTrans = ((im.size[1] * block_size) - (height * scale)) / 2.0

    translate = "translate(" + str(xTrans) + " " + str(yTrans) + ")"

    logo_scale_container = etree.SubElement(doc, 'g', transform=translate + " " + scale_str)

    for element in logo.getchildren():
        logo_scale_container.append(element)

    # ElementTree 1.2 doesn't write the SVG file header errata, so do that manually
    f = open(output_file, 'w')
    f.write('<?xml version=\"1.0\" standalone=\"no\"?>\n')
    f.write('<!DOCTYPE svg PUBLIC \"-//W3C//DTD SVG 1.1//EN\"\n')
    f.write('\"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd\">\n')
    s = etree.tostring(doc, encoding='unicode')
    print("type of s:", type(s))
    f.write(s)
    f.close()


if __name__ == '__main__':
    url = sys.argv[1]
    logo_path = sys.argv[2]
    output_file = sys.argv[3]
    generate_qr_code(url, logo_path, output_file)
