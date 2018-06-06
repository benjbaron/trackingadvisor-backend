import csv
import time
import datetime
import json
import calendar

import utils


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


client = utils.connect_to_mongo()
db = client.users
logs = db.logs

fname = '/home/ucfabb0/semantica/to_process/cab40ba2-244b-4394-aca1-4b1d87d969df_2018-05-11_131206_log.csv'
with open(fname, 'r') as f:
    reader = csv.DictReader(f, delimiter=',', quotechar='|')
    count = 0
    new_logs = []
    for line in reader:
        print(line)
        timestamp_str = line['Timestamp']
        args = line['Args']
        if args != '':
            args = json.loads(args)
        new_log = {
            'user_id': line['User'],
            'session_id': line['Session'],
            'lat': line['Lat'],
            'lon': line['Lon'],
            'ssid': line.get('ssid', ''),
            'timestamp_str': timestamp_str,
            'timestamp_local': timestamp_from_string(timestamp_str),
            'timestamp_utc': timestamp_utc_from_string(timestamp_str),
            'state': line['State'],
            'battery_charge': line.get('batteryCharge', ''),
            'battery_level': line.get('batteryLevel', ''),
            'type': line['Type'],
            'args': args
        }

        new_logs.append(new_log)
        count += 1

    # result = logs.insert_many(new_logs)
