import os, sys
import hashlib
import math
from multiprocessing.dummy import Pool as ThreadPool, Manager as ThreadManager

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import utils
import foursquare
import user_traces_db
import personal_information


UPLOAD_FOLDER = "user_traces/"
TMP_UPLOAD_FOLDER = "to_process/"

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


def get_most_likely_place(places):
    max_nb_checkins = 0
    min_distance = 100
    for place in places:
        if place['checkins'] > max_nb_checkins:
            max_nb_checkins = place['checkins']
        if place['distance'] < min_distance:
            min_distance = place['distance']

    best_score = 0
    best_place = None
    for place in places:
        score = 0.1 * place['checkins'] / max_nb_checkins + 1.5 / math.sqrt(place['distance'])
        if score > best_score:
            best_score = score
            best_place = place

    return best_place, best_score


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


def pick_place_color(place_name):
    idx = len(place_name) % len(UCL_COLORS)
    return UCL_COLORS[idx][1]


def extract_stays(raw_points, roaming_distance=100, stay_duration=5*60):
    i = 0
    S = []
    R = len(raw_points)
    while i < R:
        # print(i, R, raw_points[i])
        r_i = raw_points[i]
        pts = [j for j in range(i+1, R) if raw_points[j][2] > r_i[2] + stay_duration]
        j_star = R-1
        if pts:
            j_star = min(pts)

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
        # print("medoid: %s / %s -> %s - duration: %s (%s -> %s)" % (medoid+i, i, j_star, duration, start_hour, end_hour))
        # print("\tdiameter: %s" % (utils.compute_diameter(raw_points[i:min(j_star+1, R)])))

        S.append([raw_points[i+medoid][0], raw_points[i+medoid][1], raw_points[i][2], raw_points[j_star][2]])
        i = j_star + 1

    return S


def generate_visits(S, user_id, day):
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
            "longitude": lon,
            "latitude": lat,
            "ssid": '',
            "user_id": user_id,
            "name": "Home",
            "category": "Home",
            "type": "home",
            "user_entered": False,
            "osm_point_id": '',
            "osm_polygon_id": '',
            "venue_id": '',
            "color": UCL_COLOR_HOME[1]
        }

        # check if there is an existing home location near the recorded location
        user_place = user_traces_db.get_user_place(user_id, location, place_type="home")
        if user_place:
            home['place_id'] = user_place['place_id']
            home['address'] = user_place['address']
            home['city'] = user_place['city']

        elif start_hour <= 8 or start_hour <= 22:
            # create a new home location
            street_name, city = utils.get_address({"lat": lat, "lon": lon})
            home["city"] = city
            home["address"] = street_name

            # save the home location in the database
            place_id = user_traces_db.save_user_place_to_db(home)
            home['place_id'] = place_id

        break

    # Get the names of the other places
    prev_visit = None
    for stay in S:
        lat, lon, start, end = stay

        # distance to home location
        distance = utils.haversine(home['latitude'], home['longitude'], lat, lon)

        # populate the places
        place = {
            "longitude": lon,
            "latitude": lat,
            "ssid": '',
            "user_id": user_id
        }
        location = {"lat": lat, "lon": lon}

        if distance < 100:  # home
            place = home
            places[home['place_id']] = place

        else:               # not home
            # check if the place is in the database
            user_place = user_traces_db.get_user_place(user_id, location, place_type="place")
            if user_place:
                place_id = user_place['place_id']
                place['place_id'] = place_id
                place['name'] = user_place['name']
                place['category'] = user_place['category']
                place['user_entered'] = user_place['user_entered']
                place["longitude"] = user_place["longitude"]
                place["latitude"] = user_place["latitude"]
                place['city'] = user_place['city']
                place['address'] = user_place['address']
                place['type'] = 'place'
                place['venue_id'] = user_place['venue_id']
                place['osm_point_id'] = ''
                place['osm_polygon_id'] = ''
                places[place_id] = place
            else:
                # place not in the database, getting the closest foursquare place
                fsq_places = foursquare.get_places(location, 50, 3)
                best_place, best_score = get_most_likely_place(fsq_places)
                result = best_place

                name = result['name']
                address = result['location']['address']
                city = result['location']['city']

                place['name'] = name
                place['category'] = result['category'][0]
                place['user_entered'] = False
                place['longitude'] = result['location']['lon']
                place['latitude'] = result['location']['lat']
                place['city'] = city
                place['address'] = address
                place['osm_point_id'] = ''    # osm_point_id
                place['osm_polygon_id'] = ''  # osm_polygon_id
                place['venue_id'] = result['id']
                place['type'] = 'place'
                place['color'] = pick_place_color(place['name'])

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
        review = create_reviews_for_visit(v)
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
                for review in create_reviews_for_personal_information(pi):
                    review_id = user_traces_db.save_user_reviews_to_db(review)
                    review['review_id'] = review_id
                    reviews[review_id] = review

    print("Done processing {} personal information with {} reviews for {} places and {} visits".format(len(pis), len(reviews), len(venue_ids), len(visits)))


def create_reviews_for_visit(visit):
    review = {
        "question": "Did you visit this place?",
        "answer": 0,
        "type": 0,
        "user_id": visit['user_id'],
        "visit_id": visit['visit_id']
    }
    return review


def create_reviews_for_personal_information(pi):
    review_base = {
        "answer": 0,
        "pi_id": pi['pi_id'],
        "user_id": pi['user_id'],
        "place_id": pi['place_id']
    }

    review_personal_information = dict(review_base)
    review_personal_information['question'] = "Is the personal information correct?"
    review_personal_information['type'] = 1

    review_explanation = dict(review_base)
    review_explanation['question'] = "Is the explanation informative?"
    review_explanation['type'] = 2

    review_privacy = dict(review_base)
    review_privacy['question'] = "Is the inferred information sensitive to you?"
    review_privacy['type'] = 3

    return [review_personal_information, review_explanation, review_privacy]


def process_trace_from_db(user_id, day):
    # get the raw points from the database
    raw_points = user_traces_db.load_raw_points(user_id, day)
    # extract the stays from the raw points
    s = extract_stays(raw_points)
    generate_visits(s, user_id, day)
    # save_user_update_to_db(user_update)


def process_all_tmp_user_traces():
    # put the new traces in the database
    tmp_trace_files = glob.glob(TMP_UPLOAD_FOLDER+"*.csv")
    for trace_file in tmp_trace_files:
        # get some information about the trace from its filename
        print(trace_file)
        pattern = r"([0-9A-F-]+)_(\d{4}-\d{2}-\d{2})_?(\d{6})?(?:.csv)?"
        m = re.search(pattern, trace_file)
        user_id = m.group(1)
        day = m.group(2)

        # load the trace in the database
        user_traces_db.save_user_trace_to_db(trace_file)

        # process the trace from the database starting from the beginning of the day
        process_trace_from_db(user_id, day)

        # once finished, archive the file in the user folder
        directory = os.path.join(UPLOAD_FOLDER, user_id)
        if not os.path.exists(directory):
            os.makedirs(directory)
        print(directory)
        os.rename(trace_file, os.path.join(directory, os.path.basename(trace_file)))


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

    if arg == 'user':
        if len(sys.argv) != 4:
            print("Error - you should provide a valid user id and day (yyyy-mm-dd)")
            sys.exit(0)

        user_id = sys.argv[2]
        day = sys.argv[3]
        process_trace_from_db(user_id, day)

    else:
        print("Error - specify an argument search")
        sys.exit(0)

