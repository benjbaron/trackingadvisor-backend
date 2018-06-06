import os, shutil
import csv
import sys
import re
import time
import random
import glob
import hashlib
import math
import logging
import json
from operator import add
from multiprocessing.dummy import Pool as ThreadPool, Manager as ThreadManager
from pymongo import MongoClient

import utils
import foursquare
import user_traces_db
import personal_information

UPLOAD_FOLDER = "user_traces/"
TMP_UPLOAD_FOLDER = "to_process/"


def get_raw_points(path):
    raw_points = []
    with open(path) as f:
        f.readline()  # skip the header
        for line in f:
            line = line.split(",")
            lat = float(line[1])
            lon = float(line[2])
            ts = timestamp_from_string(line[3])
            raw_points.append((lat, lon, ts))

    return sorted(raw_points, key=lambda t: t[2])


def get_most_likely_place(user_id, start, end, user_places):
    max_total_visit_duration = 0
    most_likely_place = None
    for user_place in user_places:
        total_visit_duration = get_total_visit_duration_at_place(user_id, user_place, start, end)
        if total_visit_duration > max_total_visit_duration:
            max_total_visit_duration = total_visit_duration
            most_likely_place = user_place

    return most_likely_place


def get_total_visit_duration_at_place(user_id, user_place, start, end):
    place_id = user_place['place_id']
    visits_at_place = user_traces_db.load_user_visits_at_place(user_id, place_id)
    total_visit_duration = 0

    start = utils.seconds_since_start_of_day(start)
    end = utils.seconds_since_start_of_day(end)

    for v in visits_at_place:
        if not v['d_utc'] or not v['a_utc']:
            continue

        sod = utils.start_of_day_str(v['day'])
        eod = utils.end_of_day_str(v['day'])
        arrival_local = utils.seconds_since_start_of_day(max(sod, v['a'] - v['a_utc']))
        departure_local = utils.seconds_since_start_of_day(min(eod, v['d'] - v['d_utc']))

        if departure_local + 3600 < start or arrival_local - 3600 > end:
            continue

        duration = min(end, departure_local+3600) - max(start, arrival_local-3600)
        total_visit_duration += duration
    return total_visit_duration


def extract_stays(raw_points, roaming_distance=150, stay_duration=3 * 60):
    i = 0
    S = []
    R = len(raw_points)

    if R == 1:  # if only one point
        return S

    while i < R:
        r_i = raw_points[i]
        pts = [j for j in range(i + 1, R) if raw_points[j][2] > r_i[2] + stay_duration]
        j_star = R - 1
        if pts:
            j_star = min(pts)

        if i == j_star:
            break

        diameter = utils.compute_diameter(raw_points[i:j_star])
        avg_speed = utils.compute_average_speeds(raw_points[i:j_star + 1])
        average_inter_distance = utils.compute_average_inter_distance(raw_points[i:j_star])

        if diameter > roaming_distance or average_inter_distance > 0.75 * roaming_distance or avg_speed > 1.1:
            i += 1
            continue

        j_star = max([j for j in range(i + 1, R) if utils.compute_diameter(raw_points[i:j]) < roaming_distance])
        medoid = utils.compute_medoid(raw_points[i:j_star])

        ts_start = raw_points[i][2]
        ts_start_local = raw_points[i][3]
        ts_end = raw_points[j_star][2]
        ts_end_local = raw_points[j_star][3]
        nb_steps = sum([pt[5] for pt in raw_points[i:j_star + 1]])

        print("UTC: %s -> %s, local: %s -> %s" % (
        utils.hm(ts_start), utils.hm(ts_end), utils.hm(ts_start_local), utils.hm(ts_end_local)))

        S.append(
            [raw_points[i + medoid][0], raw_points[i + medoid][1], ts_start, ts_end, i, j_star + 1, nb_steps, avg_speed,
             average_inter_distance, ts_start_local, ts_end_local])
        i = j_star + 1

    return S


def generate_visits(S, user_id, day, pool):
    if not S:
        return

    visits = {}
    places = {}
    moves = {}
    pis = {}

    # Get the names of the other places
    prev_visit = None
    prev_place = None
    for stay in S:
        lat, lon, start, end, start_idx, end_idx, nb_steps, avg_speed, average_inter_distance, start_local, end_local = stay

        # populate the places
        place = {
            "longitude": lon,
            "latitude": lat,
            "ssid": '',
            "user_id": user_id,
            "user_entered": False,
            "osm_point_id": '',
            "osm_polygon_id": ''
        }
        location = {"lat": lat, "lon": lon}

        # check that there is at least two points
        nb_points = end_idx - start_idx
        if nb_points < 2:
            print("too little points")
            continue

        # check if the place is in the database
        user_places = user_traces_db.get_user_place(user_id, location, distance=250, limit=5)
        user_place = get_most_likely_place(user_id, start_local, end_local, user_places)

        if user_place:  # there is a user place in the vicinity
            place_id = user_place['place_id']
            place['place_id'] = place_id
            place['name'] = user_place['name']
            place['category'] = user_place['category']
            place['user_entered'] = user_place['user_entered']
            place['longitude'] = user_place['longitude']
            place['latitude'] = user_place['latitude']
            place['city'] = user_place['city']
            place['address'] = user_place['address']
            place['type'] = 'place'
            place['color'] = user_place['color']
            place['venue_id'] = user_place['venue_id']
            place['emoji'] = user_place['emoji']
            place['icon'] = user_place['icon']
            place['category_id'] = user_place['category_id']
            place['osm_point_id'] = ''
            place['osm_polygon_id'] = ''
            places[place_id] = place
        else:
            # place not in the database, getting the closest foursquare place
            fsq_places = foursquare.get_places(location, 200, 5)

            if fsq_places:
                result = fsq_places[0]  # result is ordered by decreasing likelihood

                name = result['name']
                address = result['location']['address']
                city = result['location']['city']

                place['name'] = name
                place['category'] = result['category'][0]
                place['longitude'] = result['location']['lon']
                place['latitude'] = result['location']['lat']
                place['city'] = city
                place['address'] = address
                place['venue_id'] = result['id']
                place['type'] = 'place'
                place['color'] = utils.pick_place_color(place['name'])
                place['emoji'] = result['emoji']
                place['icon'] = result['icon']
                place['category_id'] = result['category_id']
            else:
                # filter the place out if few number of steps and no places
                street_name, city = utils.get_address({"lat": lat, "lon": lon})

                if not city or city == '':
                    continue

                place['category'] = "User place"
                place['type'] = 'place'
                place['venue_id'] = ''
                place['city'] = city
                place['address'] = street_name
                place['longitude'] = lon
                place['latitude'] = lat
                place['name'] = "Place in %s" % city
                place['emoji'] = "🏠"
                place['icon'] = "home"
                place['color'] = utils.pick_place_color('home')

            # save the place in the database
            place_id = user_traces_db.save_user_place_to_db(place)
            place['place_id'] = place_id
            places[place_id] = place

        if prev_visit and prev_visit['place_id'] == place['place_id']:
            # aggregate with the previous visit
            visit = prev_visit
            visit['departure'] = end
        else:
            # create a new visit
            visit = {
                "place_id": place['place_id'],
                "arrival": start,
                "original_arrival": start,
                "departure": end,
                "confidence": 1.0,
                "latitude": lat,
                "longitude": lon,
                "day": day,
                "user_id": user_id,
                "arrival_utc_offset": start - start_local,
                "departure_utc_offset": end - end_local,
                "original_place_id": place['place_id']
            }

            # save the previous visit to the database
            if prev_visit:
                # get_visits_at_place(prev_visit)
                visit_id = user_traces_db.save_user_visit_to_db(prev_visit)
                a_utc_offset = prev_visit['arrival_utc_offset']
                d_utc_offset = prev_visit['arrival_utc_offset']
                print("[%s -> %s] %s  %s" % (
                utils.hm(prev_visit['arrival'] - a_utc_offset), utils.hm(prev_visit['departure'] - d_utc_offset),
                prev_place['emoji'], prev_place['name']))
                prev_visit['visit_id'] = visit_id
                visits[visit_id] = prev_visit

                # create a new move
                move = {
                    "departure_date": prev_visit['departure'],
                    "arrival_date": start,
                    "activity": "Unknown",
                    "activity_confidence": 1.0,
                    "departure_place_id": prev_visit['place_id'],
                    "arrival_place_id": visit['place_id'],
                    "day": day,
                    "user_id": user_id
                }

                # save the move to the database
                move_id = user_traces_db.save_user_move_to_db(move)
                moves[move_id] = move

        prev_visit = visit
        prev_place = place

    # add the last visit to the database
    # get_visits_at_place(prev_visit)
    if prev_visit:
        visit_id = user_traces_db.save_user_visit_to_db(prev_visit)
        a_utc_offset = prev_visit['arrival_utc_offset']
        d_utc_offset = prev_visit['arrival_utc_offset']
        print("[%s -> %s] %s  %s" % (
        utils.hm(prev_visit['arrival'] - a_utc_offset), utils.hm(prev_visit['departure'] - d_utc_offset),
        prev_place['emoji'], prev_place['name']))

        prev_visit['visit_id'] = visit_id
        visits[visit_id] = prev_visit

    # detect home and work locations
    home_id, work_ids = determine_home_work_places(user_id)
    print("home id: %s, work id: %s" % (home_id, work_ids))

    if home_id and home_id in places:
        print("\tHome: %s" % places[home_id]['name'])
        home_place = user_traces_db.load_user_place(user_id, home_id)
        if home_place['pt'] == 0:  # default value - nothing
            user_traces_db.update_place_type(user_id, home_id, 1)  # probably home

    if work_ids and len(work_ids) > 0:
        for work_id in work_ids:
            if work_id in places:
                print("\tWork: %s" % places[work_id]['name'])
                work_place = user_traces_db.load_user_place(user_id, work_id)
                if work_place['pt'] == 0:  # default value - nothing
                    user_traces_db.update_place_type(user_id, work_id, 3)  # probably work

    # get the personal information for all the places visited
    place_ids = [p['place_id'] for p in places.values()]
    venue_ids = [places[p]['venue_id'] for p in place_ids]

    result = pool.map_async(personal_information.get_personal_information, venue_ids)
    result.wait()
    res_pi = result.get()

    for i in range(len(res_pi)):
        place_id = place_ids[i]
        for c, v in res_pi[i].items():
            for pi in v:
                pi['user_id'] = user_id
                pi['place_id'] = place_id
                pi['category_id'] = c
                pi['source'] = list(pi['source'])
                pi_id = user_traces_db.save_user_personal_information_to_db(pi)

                pi['pi_id'] = pi_id
                pis[pi_id] = pi
                user_traces_db.create_or_update_aggregate_personal_information(user_id, pi, pi_id)

    print("Done processing {} personal information with {} places and {} visits".format(len(pis), len(venue_ids),
                                                                                        len(visits)))


def process_aggregated_personal_information(user_id):
    pis = user_traces_db.load_all_user_personal_information(user_id)
    for update_pi in pis:
        pi_id = update_pi['piid']
        pi = {
            "user_id": user_id,
            "name": update_pi['name'],
            "icon": update_pi['icon'],
            "category_id": update_pi['picid'],
            "description": update_pi['d'],
            "source": update_pi['s'],
            "explanation": update_pi['e'],
            "rating": update_pi['r'],
            "privacy": update_pi['p']
        }
        add_or_create_aggregate_personal_information(user_id, pi, pi_id)
    print("Done with %s personal information" % len(pis))


def create_user_challenge(user_id, day):
    visits = user_traces_db.load_user_visits(user_id, day)
    challenges = []
    places = set()
    date = int(time.time())
    for v in visits:
        visit_id = v['vid']
        place_id = v['pid']

        if place_id in places:
            continue

        rv, rpi = user_traces_db.get_user_reviews_for_visit(user_id, visit_id)
        places.add(place_id)

        if len(rpi) == 0:
            challenges.append({
                "day": day,
                "user_id": user_id,
                "date_created": date,
                "place_id": place_id,
                "visit_id": visit_id,
                "place_number": 1
            })
            continue

        unique_pi = set(r['pi_id'] for r in rpi)
        # pick random personal information
        chosen_pi = random.sample(unique_pi, min(2, len(unique_pi)))

        i = 1
        for pi_id in chosen_pi:
            challenge = {
                "day": day,
                "user_id": user_id,
                "date_created": date,
                "visit_id": visit_id,
                "place_id": place_id,
                "personal_information_id": pi_id,
                "place_number": i
            }
            challenges.append(challenge)
            i += 1

    for challenge in challenges:
        user_traces_db.save_user_review_challenge_to_db(challenge)

    return challenges


def process_trace_from_db(user_id, day, pool, logging):
    # get the raw points from the database
    raw_points = user_traces_db.load_raw_points(user_id, day)

    # get the last point from the previous day
    previous_day_raw_points = user_traces_db.load_raw_points(user_id, utils.previous_day(day))
    if previous_day_raw_points:
        last_point = previous_day_raw_points[-1]  # take the last raw point of the previous day
        utc_offset = last_point[3] - last_point[2]  # time difference between the local and UTC times
        last_point[3] = utils.next_day_ts(utils.start_of_day(last_point[3]))
        last_point[2] = last_point[3] - utc_offset
        raw_points.insert(0, last_point)

    # extract the stays from the raw points
    logging.info("Extracting the stay points")
    s = extract_stays(raw_points)

    # generate the visits
    logging.info("Generating the visits")
    generate_visits(s, user_id, day, pool)


def save_log_in_mongo(fname):
    client = utils.connect_to_mongo()
    db = client.users
    logs = db.logs

    pattern = r"^(?:.*)\/(.*)\_(.*)\_(.*)\_log\.csv$"
    m = re.match(pattern, fname)
    if not m:
        return None, None

    uid = m.group(1)
    day = m.group(2)

    with open(fname, 'r') as f:
        reader = csv.DictReader(f, delimiter=',', quotechar='|')
        new_logs = []
        for line in reader:
            timestamp_str = line['Timestamp']
            try:
                timestamp_local = utils.timestamp_from_string(timestamp_str)
            except:
                continue

            args = line['Args']
            if args != '':
                args = json.loads(args)
            new_log = {
                'user_id': line['User'],
                'day': utils.timestamp_to_day_str(timestamp_local),
                'session_id': int(line['Session']),
                'lat': float(line['Lat']),
                'lon': float(line['Lon']),
                'ssid': line.get('ssid', ''),
                'timestamp_str': timestamp_str,
                'timestamp_local': timestamp_local,
                'timestamp_utc': utils.timestamp_utc_from_string(timestamp_str),
                'state': line.get('State', ''),
                'battery_charge': line.get('batteryCharge', -1),
                'battery_level': float(line.get('batteryLevel', -1)),
                'type': line.get('Type', ''),
                'args': args
            }

            new_logs.append(new_log)

        if len(new_logs) > 0:
            res = logs.insert_many(new_logs)
            print("Added %s logs to mongo from %s" % (len(res.inserted_ids), fname))

    return uid, day


def process_all_tmp_user_traces(logging):
    # put the new traces in the database
    tmp_trace_files = glob.glob(TMP_UPLOAD_FOLDER + "*.csv")
    pool = ThreadPool(20)
    log_pattern = r"^(?:.*)\_log\.csv$"

    for trace_file in tmp_trace_files:
        if re.match(log_pattern, trace_file):
            # this is a log file to process
            # print("Processing log file %s" % trace_file)
            uid, day = save_log_in_mongo(trace_file)

            if uid is None:
                continue

            # log the processing
            logging.info("[%s] LOG %s %s" % (uid, day, trace_file))

            # once finished, archive the file in the user folder
            directory = os.path.join(UPLOAD_FOLDER, uid)
            if not os.path.exists(directory):
                os.makedirs(directory)

            shutil.move(trace_file, os.path.join(directory, os.path.basename(trace_file)))
            continue

        # save the raw points in the database
        uids, days = user_traces_db.save_user_trace_to_db(trace_file)

        # process the trace from the database starting from the beginning of the day
        for uid in uids:
            for day in days:
                logging.info("process uid %s for day %s" % (uid, day))
                process_trace_from_db(uid, day, pool, logging)

                # log the processing
                logging.info("[%s] TRACE %s %s" % (uid, day, trace_file))

            # once finished, archive the file in the user folder
            directory = os.path.join(UPLOAD_FOLDER, uid)
            if not os.path.exists(directory):
                os.makedirs(directory)

            shutil.move(trace_file, os.path.join(directory, os.path.basename(trace_file)))


def update_place_icons():
    user_places = user_traces_db.load_all_places()
    for place in user_places:
        if place['type'] == 'home':
            place['emoji'] = "🏠"
            place['icon'] = "home"
        else:
            venue_id = place['venue_id']
            foursquare.get_icon_for_venue(venue_id)
            emoji, icon = foursquare.get_icon_for_venue(venue_id)
            place['emoji'] = emoji
            place['icon'] = icon

        user_traces_db.update_user_place(place)


def determine_home_work_places(user_id, nb_days=3, hour_threshold=3):
    home_hours = [(0, 7), (20, 23)]
    work_hours = [(9, 18)]
    home_threshold = 60 * 60 * hour_threshold * nb_days  # 4 hour threshold default
    work_threshold = 0

    places = {}

    # get all the days
    # compute the unique places visited and the time spend at these places
    days = []
    day = utils.previous_day(utils.today_string())
    for i in range(nb_days):
        days.append(day)
        day = utils.previous_day(day)

    for day in days:
        weekend = utils.is_weekend(day)
        visits = user_traces_db.load_user_visits_utc(user_id, day)

        if len(visits) == 0:
            return None, None

        if not weekend:
            work_threshold += 60 * 60 * hour_threshold

        # fix the last visit
        last_visit = visits[-1]
        utc_offset = last_visit['d_utc']

        if not utc_offset:
            return None, None

        last_visit_end = last_visit['d'] - utc_offset  # departure_utc - utc_offset
        last_visit_end = utils.end_of_day(last_visit_end)
        visits[-1]['d'] = last_visit_end + utc_offset

        for visit in visits:
            start = max(utils.start_of_day_str(day), visit['a'] - visit['d_utc'])  # arrival_utc and utc_offset
            end = visit['d'] - visit['d_utc']  # departure_utc and utc_offset
            place_id = visit['pid']

            # place = user_traces_db.load_user_place(user_id, place_id)
            # print("%s [%s %s -> %s %s] %s" % (day, utils.timestamp_to_day_str(start), utils.hm(start), utils.timestamp_to_day_str(end), utils.hm(end), place['name']))

            work_seconds = 0
            if not weekend:
                work_seconds = utils.seconds_in_hour_range(start, end, work_hours)
            home_seconds = utils.seconds_in_hour_range(start, end, home_hours)
            if place_id not in places:
                places[place_id] = [0, 0]
            places[place_id] = map(add, places[place_id], [home_seconds, work_seconds])

    new_places = {}
    for pid, p in places.items():
        new_places[pid] = list(p)

    # Determine the work and home places
    home_place = None
    home_places = [(pid, p[0]) for pid, p in new_places.items() if p[0] > home_threshold]
    if len(home_places):
        home_place = max(home_places, key=lambda x: x[1])

    # can have multiple work locations
    work_places = [pid for pid, p in new_places.items() if p[1] > work_threshold]

    return home_place[0] if home_place else None, work_places


def create_screenshot_data():
    user_test = user_traces_db.load_user_info_test()
    user_id = ""
    if not user_test:
        print("create a new test user")
        user = {
            "date_added": int(time.time()),
            "test": True
        }
        user_id = user_traces_db.save_user_info_to_db(user)
    else:
        print("retriving existing test user")
        user_id = user_test['user_id']

    print("test user id: %s" % user_id)
    print("delete all user records")
    user_traces_db.delete_all_records(user_id)

    day = utils.today_string()

    user_visits = [
        {"name": "Home", "venue_id": None, "arrival": "00:00", "departure": "7:21", "color": "#EA7600"},
        {"name": "Euston Station (EUS)", "venue_id": "4acbc300f964a52058c520e3", "arrival": "9:07", "departure": "9:18",
         "color": "#500778"},
        {"name": "UCLU George Farha Café", "venue_id": "4de64d037d8b53987c5d31cb", "arrival": "9:23",
         "departure": "9:30", "color": "#500778"},
        {"name": "UCL Pearson Building", "venue_id": "4bcd62910687ef3b90d8e0cc", "arrival": "9:32",
         "departure": "13:42", "color": "#500778"}]

    for visit in user_visits:
        print("visit: %s" % visit)
        name = visit['name']
        venue_id = visit['venue_id']
        departure = visit['departure']
        arrival = visit['arrival']
        start = utils.today_timestamp_at_time(arrival)
        end = utils.today_timestamp_at_time(departure)

        place = {
            "name": name,
            "longitude": -0.108476,
            "latitude": 51.549093,
            "ssid": '',
            "user_id": user_id,
            "user_entered": False,
            "osm_point_id": '',
            "osm_polygon_id": ''
        }

        if venue_id:
            result = foursquare.get_place(venue_id)
            address = result['location']['address']
            city = result['location']['city']

            place['category'] = result['category'][0]
            place['longitude'] = result['location']['lon']
            place['latitude'] = result['location']['lat']
            place['city'] = city
            place['address'] = address
            place['venue_id'] = result['id']
            place['type'] = 'place'
            place['color'] = visit['color']
            place['emoji'] = result['emoji']
            place['icon'] = result['icon']

        else:
            place["ssid"] = '',
            place["user_id"] = user_id,
            place["name"] = "Home",
            place["category"] = "Home",
            place["type"] = "home",
            place["user_entered"] = False,
            place["osm_point_id"] = '',
            place["osm_polygon_id"] = '',
            place["venue_id"] = '',
            place["color"] = visit['color'],
            place["icon"] = "home",
            place["emoji"] = "🏠"

        # save the place in the database
        place_id = user_traces_db.save_user_place_to_db(place)
        place['place_id'] = place_id
        visit['place_id'] = place_id

        visit = {
            "place_id": place['place_id'],
            "arrival": start,
            "original_arrival": start,
            "departure": end,
            "confidence": 1.0,
            "latitude": 0.0,
            "longitude": 0.0,
            "day": day,
            "user_id": user_id,
            "original_place_id": place['place_id']
        }

        visit_id = user_traces_db.save_user_visit_to_db(visit)
        visit['visit_id'] = visit_id

    place_ids = [v['place_id'] for v in user_visits if v['venue_id']]
    venue_ids = [v['venue_id'] for v in user_visits if v['venue_id']]
    print("venue_ids: %s" % venue_ids)

    pool = ThreadPool(20)
    result = pool.map_async(personal_information.get_personal_information, venue_ids)
    result.wait()
    res_pi = result.get()

    pis = {}
    for i in range(len(res_pi)):
        place_id = place_ids[i]
        for c, v in res_pi[i].items():
            for pi in v:
                pi['user_id'] = user_id
                pi['place_id'] = place_id
                pi['category_id'] = c
                pi['source'] = list(pi['source'])
                pi_id = user_traces_db.save_user_personal_information_to_db(pi)
                pi['pi_id'] = pi_id

                pis[pi_id] = pi
                user_traces_db.create_or_update_aggregate_personal_information(user_id, pi, pi_id)

    print("Done processing {} personal information with {} places and {} visits".format(len(pis), len(venue_ids),
                                                                                        len(user_visits)))


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print("Error - you should choose an argument:")
        base = sys.argv[0]
        print('\t{} user-trace file'.format(base))
        print('\t{} user user_id day (yyyy-mm-dd)'.format(base))
        sys.exit(0)

    arg = sys.argv[1]
    if arg == 'file':
        if len(sys.argv) != 3:
            print("Error - you should provide a valid user trace file")
            sys.exit(0)

        trace_file = sys.argv[2]
        print("Save user trace {} into DB".format(trace_file))
        user_traces_db.save_user_trace_to_db(trace_file)

    elif arg == 'user':
        if len(sys.argv) != 4:
            print("Error - you should provide a valid user id and day (yyyy-mm-dd)")
            sys.exit(0)

        os.chdir('/home/ucfabb0/code/semantica-docker/src/')

        user_id = sys.argv[2]
        day = sys.argv[3]
        pool = ThreadPool(20)
        process_trace_from_db(user_id, day, pool)

    elif arg == 'test':
        filepath = '/home/ucfabb0/code/semantica-docker/app/scripts/test.csv'
        with open(filepath, 'a') as f:
            f.write("%s\n" % time.time())

    elif arg == 'all':
        os.chdir('/home/ucfabb0/code/semantica-docker/app/')
        filepath = '/home/ucfabb0/semantica/cronlogs'

        process_all_tmp_user_traces(filepath)

    elif arg == 'challenge':
        if len(sys.argv) != 4:
            print("Error - you should provide a valid user id and day (yyyy-mm-dd)")
            sys.exit(0)

        user_id = sys.argv[2]
        day = sys.argv[3]
        challenge = create_user_challenge(user_id, day)

        user_traces_db.load_user_review_challenge(user_id, day)
        print("Done")

    elif arg == 'delete':
        if len(sys.argv) != 3:
            print("Error - you should provide a valid user id ")
            sys.exit(0)

        user_id = sys.argv[2]
        user_traces_db.delete_all_records(user_id)

    elif arg == 'aggregated':
        if len(sys.argv) != 3:
            print("Error - you should provide a valid user id")
            sys.exit(0)

        user_id = sys.argv[2]
        process_aggregated_personal_information(user_id)

    elif arg == 'icon':
        update_place_icons()

    elif arg == 'screenshot':
        create_screenshot_data()

    elif arg == 'test-home':
        if len(sys.argv) != 3:
            print("Error - you should provide a valid user id")
            sys.exit(0)

        user_id = sys.argv[2]
        print(determine_home_work_places(user_id))

    else:
        print("Error - specify an argument search")
        sys.exit(0)

