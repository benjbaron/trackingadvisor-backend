import os
import sys
import re
import time
import glob
import hashlib
import math
from multiprocessing.dummy import Pool as ThreadPool, Manager as ThreadManager

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import utils
import foursquare
import user_traces_db
import personal_information


UPLOAD_FOLDER = "/home/ucfabb0/semantica/user_traces_tmp/"
TMP_UPLOAD_FOLDER = "/home/ucfabb0/semantica/to_process_tmp/"


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


def extract_stays(raw_points, roaming_distance=100, stay_duration=10*60):
    i = 0
    S = []
    R = len(raw_points)

    if R == 1:  # if only one point
        return S

    while i < R:
        # print(i, R, raw_points[i])
        r_i = raw_points[i]
        pts = [j for j in range(i+1, R) if raw_points[j][2] > r_i[2] + stay_duration]
        j_star = R-1
        if pts:
            j_star = min(pts)

        if i == j_star:
            break

        print("i: %s, j_star: %s, len(raw_points): %s" % (i, j_star, len(raw_points)))
        print(raw_points[i:j_star])
        diameter = utils.compute_diameter(raw_points[i:j_star])
        # print(i, j_star, R, diameter)

        if diameter > roaming_distance:
            # print("new medoid, %s -- %s" % (diameter, raw_points[i:j_star]))
            i += 1
            continue

        j_star = max([j for j in range(i+1, R) if utils.compute_diameter(raw_points[i:j]) < roaming_distance])
        medoid = utils.compute_medoid(raw_points[i:j_star+1])

        duration = raw_points[j_star][2] - raw_points[i][2]
        start_hour = utils.datetime_from_timestamp(raw_points[i][2]).hour
        end_hour = utils.datetime_from_timestamp(raw_points[j_star][2]).hour
        print("medoid: %s / %s -> %s - duration: %s (%s -> %s)" % (medoid+i, i, j_star, duration, start_hour, end_hour))
        print("\tdiameter: %s" % (utils.compute_diameter(raw_points[i:min(j_star+1, R)])))

        S.append([raw_points[i+medoid][0], raw_points[i+medoid][1], raw_points[i][2], raw_points[j_star][2]])
        i = j_star + 1

    return S


def generate_visits(S, user_id, day):
    if not S:
        return

    visits = {}
    places = {}
    moves  = {}
    pis = {}
    reviews = {}

    home = {}
    # detect home location
    # TODO: more evolved model to compute the home location
    #       based on a statistical analysis of all the locations within these time ranges
    for stay in S:
        lat, lon, start, end = stay
        location = {"lat": lat, "lon": lon}
        start_hour = utils.datetime_from_timestamp(start).hour
        end_hour = utils.datetime_from_timestamp(end).hour

        home = {
            "ssid": '',
            "user_id": user_id,
            "name": "Home",
            "category": "Home",
            "type": "home",
            "user_entered": False,
            "osm_point_id": '',
            "osm_polygon_id": '',
            "venue_id": '',
            "color": utils.pick_place_color('home')
        }

        # check if there is an existing home location near the recorded location
        user_place = user_traces_db.get_user_place(user_id, location)
        if user_place:
            home['place_id'] = user_place['place_id']
            home['address'] = user_place['address']
            home['city'] = user_place['city']
            home['longitude'] = user_place['longitude']
            home['latitude'] = user_place['latitude']

        elif start_hour < 7 or start_hour > 22:
            # create a new home location
            street_name, city = utils.get_address({"lat": lat, "lon": lon})
            home['city'] = city
            home['address'] = street_name
            home['longitude'] = lon
            home['latitude'] = lat

            # save the home location in the database
            place_id = user_traces_db.save_user_place_to_db(home)
            home['place_id'] = place_id

        break

    # Get the names of the other places
    prev_visit = None
    for stay in S:
        lat, lon, start, end = stay

        # distance to home location
        distance = -1
        if 'place_id' in home and home['place_id']:
            distance = utils.haversine(home['latitude'], home['longitude'], lat, lon)

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

        if distance != -1 and distance < 100:  # home
            place = home
            places[home['place_id']] = place

        else:               # not home
            # check if the place is in the database
            user_place = user_traces_db.get_user_place(user_id, location)
            if user_place:
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
                place['osm_point_id'] = ''
                place['osm_polygon_id'] = ''
                places[place_id] = place
            else:
                # place not in the database, getting the closest foursquare place
                fsq_places = foursquare.get_places(location, 200, 5)

                if fsq_places:
                    result = fsq_places[0]  # result is ordered by likelihood

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
                else:
                    street_name, city = utils.get_address({"lat": lat, "lon": lon})
                    place['category'] = "User place"
                    place['type'] = 'place'
                    place['venue_id'] = ''
                    place['city'] = city
                    place['address'] = street_name
                    place['longitude'] = lon
                    place['latitude'] = lat
                    place['name'] = "Place in %s" % city
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
                "departure": end,
                "confidence": 1.0,
                "latitude": lat,
                "longitude": lon,
                "day": day,
                "user_id": user_id
            }

            # save the previous visit to the database
            if prev_visit:
                visit_id = user_traces_db.save_user_visit_to_db(prev_visit)
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

    # add the last visit to the database
    visit_id = user_traces_db.save_user_visit_to_db(prev_visit)
    prev_visit['visit_id'] = visit_id
    visits[visit_id] = prev_visit

    # Create the set of reviews for the visits
    for k,v in visits.items():
        review = personal_information.create_reviews_for_visit(v)
        review_id = user_traces_db.save_user_reviews_to_db(review)
        review['review_id'] = review_id
        reviews[review_id] = review

    # get the personal information for all the places visited
    place_ids = [p['place_id'] for p in places.values()]
    venue_ids = [places[p]['venue_id'] for p in place_ids]

    pool = ThreadPool(20)
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

                # create the set of reviews for the personal information
                for review in personal_information.create_reviews_for_personal_information(pi):
                    review_id = user_traces_db.save_user_reviews_to_db(review)
                    review['review_id'] = review_id
                    reviews[review_id] = review

    print("Done processing {} personal information with {} reviews for {} places and {} visits".format(len(pis), len(reviews), len(venue_ids), len(visits)))


def process_trace_from_db(user_id, day):
    # get the raw points from the database
    raw_points = user_traces_db.load_raw_points(user_id, day)
    # extract the stays from the raw points
    s = extract_stays(raw_points)
    generate_visits(s, user_id, day)
    # save_user_update_to_db(user_update)


def process_all_tmp_user_traces(filepath):
    # put the new traces in the database
    f = open(filepath, 'a')
    tmp_trace_files = glob.glob(TMP_UPLOAD_FOLDER+"*.csv")

    for trace_file in tmp_trace_files:
        print("Processing trace file %s" % trace_file)

        # save the raw points in the database
        uids, days = user_traces_db.save_user_trace_to_db(trace_file)

        # process the trace from the database starting from the beginning of the day
        for uid in uids:
            for day in days:
                process_trace_from_db(uid, day)

                # log the processing
                f.write("%s;%s;%s;%s\n" % (time.time(), uid, day, trace_file))

        # once finished, archive the file in the user folder
        directory = os.path.join(UPLOAD_FOLDER, uid)
        if not os.path.exists(directory):
            os.makedirs(directory)
        os.rename(trace_file, os.path.join(directory, os.path.basename(trace_file)))

    f.close()


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

        user_id = sys.argv[2]
        day = sys.argv[3]
        process_trace_from_db(user_id, day)

    elif arg == 'test':
        filepath = '/home/ucfabb0/code/semantica-docker/app/scripts/test.csv'
        with open(filepath, 'a') as f:
            f.write("%s\n" % time.time())

    elif arg == 'all':
        filepath = '/home/ucfabb0/semantica/cronlogs'

        process_all_tmp_user_traces(filepath)

    elif arg == 'delete':
        if len(sys.argv) != 3:
            print("Error - you should provide a valid user id ")
            sys.exit(0)

        user_id = sys.argv[2]
        user_traces_db.delete_all_records(user_id)

    else:
        print("Error - specify an argument search")
        sys.exit(0)

