import os
import sys
import time
import re
import psycopg2
import csv
import psycopg2.extras
from shapely.geometry import shape
from shapely.geometry.multipolygon import MultiPolygon
import fiona
import utils


DB_HOSTNAME = 'colossus07'
EPSG = 27700  # OSGB 1936 / British National Grid -- United Kingdom Ordnance Survey


def split(s):
    reader = csv.reader([s], skipinitialspace=True)
    return list(reader)[0]


def import_shapefile_to_db(filepath):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="census_uk", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    count = 0
    shp = fiona.open(filepath)
    nb_tracts = len(shp)
    for feature in shp:
        type = feature['type']
        id = feature['id']
        geom = shape(feature['geometry'])
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        prop = feature['properties']
        geo_code = prop['geo_code']
        label = prop['label']

        query_string = """INSERT INTO tracts
                (geo_code, geom)
                VALUES (%s, ST_GeomFromText(%s, %s))
                ON CONFLICT DO NOTHING;"""
        data = (geo_code, geom.wkt, EPSG)
        cursor.execute(query_string, data)

        count += 1
        if count % 100 == 0:
            utils.print_progress("Done: %.2f" % (100.0 * count / nb_tracts))
        # if count == 10:
        #     break

    connection.commit()


def update_tract_info_in_db(filepath):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="census_uk", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    with open(filepath, 'r') as f:
        header = split(f.readline().strip())
        description = split(f.readline().strip())  # description of the fields
        print(len(header), len(description))
        print(header[:6])
        print(description[:6])
        for i in range(0, len(header)-1):
            print(header[i], description[i])
            # ALTER TABLE stats ADD COLUMN %s int;
            # add codes table with the correspondence of the codes

        count = 0
        for line in f:
            fields = split(line.strip())
            d = dict(zip(header, fields))

            print(fields[:6])

            # print(d)
            geo_code = d['GEO_CODE']
            geo_type = d['GEO_TYPE']
            geo_type_2 = d['GEO_TYP2']
            geo_label = d['GEO_LABEL']

            if geo_type_2 == 'OASA':  # filter Output Areas and Small Areas (OASA)
                # alter tracts database to update the tract information
                query_string = """UPDATE tracts SET geo_type = %s,
                                                    geo_typ2 = %s,
                                                    geo_label = %s
                        WHERE geo_code = %s;"""
                data = (geo_type, geo_type_2, geo_label, geo_code)
                cursor.execute(query_string, data)

                print(geo_label, geo_code, d['CDU_ID'], d['GEO_LABEL'])

                count += 1
                if count == 100:
                    break

    connection.commit()
    print("Done for {} lines".format(count))


def import_stats_to_db(filepath):
    connection = psycopg2.connect(host=DB_HOSTNAME, database="census_uk", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    with open(filepath, 'r') as f:
        header = split(f.readline().strip())
        description = split(f.readline().strip())  # description of the fields
        print(len(header), len(description))
        for i in range(5, len(header)-1):
            print(header[i], description[i])
            # ALTER TABLE stats ADD COLUMN %s int;
            # add codes table with the correspondence of the codes


if __name__ == '__main__':
    # shp_filename = sys.argv[1]
    stats_filename = sys.argv[1]
    # import_shapefile_to_db(shp_filename)
    update_tract_info_in_db(stats_filename)
    print("all tracts have been loaded in the database")
