import sys
import json
import gspread
# from oauth2client.client import SignedJwtAssertionCredentials
from oauth2client.service_account import ServiceAccountCredentials
import re
import psycopg2
import psycopg2.extras


print("Retrieving the spreadsheets...")

DB_HOSTNAME = "colossus07"

pattern = r"(\w+)(?:\[([a-zA-Z,_]*)\])?"
json_key = json.load(open('gdoc_keys.json'))
scope = ['https://spreadsheets.google.com/feeds']
sheet_key = "1URyAmcpwI2FPiHeZMnEV9ZjA-u_zWEqpNha8RRBbnTw"

credentials = ServiceAccountCredentials.from_json_keyfile_name('gdoc_keys.json', scope)
# credentials = SignedJwtAssertionCredentials(json_key['client_email'], json_key['private_key'].encode(), scope)
gc = gspread.authorize(credentials)


def get_name(uri):
    pattern = r".*\b\/(?:\w+\:)?([^\/:]+)\>$"
    m = re.match(pattern, uri)
    try:
        name = m.group(1).replace("_", " ")
    except AttributeError as e:
        print("Problem with uri {}".format(uri))
        return ""
    return name


def get_categories(categories, sheet_idx, start_idx):
    wks = gc.open_by_key(sheet_key).get_worksheet(sheet_idx)

    for row in wks.get_all_values()[1:]:
        for info in row[start_idx:]:
            if not info:
                continue
            m = re.search(pattern, info)
            cat, keys = m.groups()
            if cat not in categories:
                categories[cat] = set()

            if keys:
                categories[cat].update(keys.split(','))


def generate_personal_information_list():
    categories = {}
    get_categories(categories, 1, 3)
    get_categories(categories, 2, 4)

    worksheet = gc.open_by_key(sheet_key).get_worksheet(3)

    rows = []
    category_list = sorted(categories.keys(), key=str.lower)
    for cat in category_list:
        keys = categories[cat]
        for k in sorted(keys, key=str.lower):
            rows.append([cat, k])

    cell_list = worksheet.range(2, 1, len(rows), 1)
    i = 0
    for cell in cell_list:
        cell.value = rows[i][0]
        i += 1
    worksheet.update_cells(cell_list)

    cell_list = worksheet.range(2, 2, len(rows), 2)
    i = 0
    for cell in cell_list:
        cell.value = rows[i][1]
        i += 1
    worksheet.update_cells(cell_list)

    print("Done with {} rows".format(len(rows)))


def add_foursquare_personal_information_to_db():
    # 1 - get personal information associated to the foursquare category
    wks = gc.open_by_key(sheet_key).get_worksheet(1)
    categories = {}
    for row in wks.get_all_values()[1:]:
        venue_id = row[2]
        personal_information = "{%s}" % ",".join(info for info in row[3:] if info)
        categories[venue_id] = personal_information

    # 2 - connect to database to update the fields
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    for category_id, personal_information in categories.items():
        query_string = """
        UPDATE categories
        SET personal_information = %s
        WHERE category_id = %s;"""
        data = (personal_information, category_id)
        cursor.execute(query_string, data)

    connection.commit()
    print("Done")


def get_personal_information(db_name):
    sheet_idx = -1
    if db_name == 'dbpedia':
        sheet_idx = 4
    elif db_name == 'foursquare':
        sheet_idx = 5
    elif db_name == 'categories':
        sheet_idx = 6

    fname = '../supp/personal_information_{}.csv'.format(db_name)
    f_out = open(fname, 'w')

    wks = gc.open_by_key(sheet_key).get_worksheet(sheet_idx)
    header = wks.row_values(1)
    f_out.write("%s\n" % ";".join(e for e in header if e))

    for row in wks.get_all_values()[2:]:
        f_out.write("%s\n" % ";".join(row[i] for i in range(len(row)) if header[i]))

    f_out.close()
    print("Done writing in file {}".format(fname))


def dump_all_personal_information():
    sheet_idx = 3
    wks = gc.open_by_key(sheet_key).get_worksheet(sheet_idx)

    fname = '../supp/personal_information_all.csv'
    f_out = open(fname, 'w')

    header = wks.row_values(1)
    f_out.write("%s\n" % ";".join(e for e in header if e))

    for row in wks.get_all_values()[1:]:
        f_out.write("%s\n" % ";".join(row[i] for i in range(len(row)) if header[i]))

    f_out.close()
    print("Done writing in file {}".format(fname))


def save_personal_information_to_db():
    sheet_idx = 3
    wks = gc.open_by_key(sheet_key).get_worksheet(sheet_idx)

    # connect to database to add or update the fields
    connection = psycopg2.connect(host=DB_HOSTNAME, database="foursquare", user="postgres", password="postgres")
    cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)

    header = wks.row_values(1)

    count = 0
    for row in wks.get_all_values()[1:]:
        d = dict(zip(header, row))

        query_string = """
            INSERT INTO personal_information
            (name, category_icon, subcategory_name, subcategory_icon, category_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name, category_id) DO UPDATE SET 
               subcategory_name=EXCLUDED.subcategory_name, name=EXCLUDED.name, subcategory_icon=EXCLUDED.subcategory_icon
            RETURNING pi_id;"""
        data = (d.get('name', None), d.get('category_icon', None), d.get('subcategory_name', None),
                d.get('subcategory_icon', None), d.get('picid', None))

        cursor.execute(query_string, data)
        count += 1

    connection.commit()

    print("Done saving {} personal information in the database".format(count))


def get_personal_information_list():
    sheet_idx = 5
    wks = gc.open_by_key(sheet_key).get_worksheet(sheet_idx)
    res = {}
    header = wks.row_values(1)
    for h in header:
        if h in ['', 'ID']:
            continue
        res[h] = set()
    for row in wks.get_all_values()[2:]:
        for i in range(len(header)):
            h = header[i]
            if h in res and row[i] != '':
                res[h].update(row[i].split(','))

    print(res)


def get_consent_form():
    fname = '../supp/consent_form.csv'
    f_out = open(fname, 'w')

    wks = gc.open_by_key(sheet_key).get_worksheet(7)
    header = wks.row_values(1)
    f_out.write("%s\n" % ";".join(e for e in header if e))

    for row in wks.get_all_values()[1:]:
        f_out.write("%s\n" % ";".join(row[i] for i in range(len(row)) if header[i]))

    f_out.close()
    print("Done writing in file {}".format(fname))


if __name__ == '__main__':
    base = sys.argv[0]
    if len(sys.argv) == 1:
        print("Error - please specify an argument")
        sys.exit(0)

    arg = sys.argv[1]
    if arg in ['dbpedia', 'foursquare', 'categories']:
        get_personal_information(arg)
    elif arg == 'consent-form':
        get_consent_form()
    elif arg == 'list':
        get_personal_information_list()
    elif arg == 'all':
        dump_all_personal_information()
    elif arg == 'pi-db':
        save_personal_information_to_db()
    else:
        print("Error - incorrect argument (dbpedia, foursquare, categories, consent-form, list, all)")
        sys.exit(0)

