import sys
import time
import pika
import json
from geojson import Feature, Point, FeatureCollection
from multiprocessing.dummy import Pool as ThreadPool

import user_traces_db
import personal_information
import foursquare
import utils


RABBITMQ_HOST = "colossus07"


def get_basic_stats(users):
    visit_stats = user_traces_db.load_stats_places_visited()
    stats = {
        "nb_days": max(u['nb_days'] for u in users),
        "nb_users": len(users),
        "nb_places": visit_stats['nb_places'],
        "nb_visits": visit_stats['nb_visits']
    }
    return stats


def get_all_users():
    return user_traces_db.load_all_users()


def get_all_visits_anonymous_geojson():
    visits = user_traces_db.load_all_visits_anonymous()
    features = []
    for v in visits:
        features.append(Feature(geometry=Point((v['lon'], v['lat'])),
                                properties={"dur": v['dur'], "nb_visits": v['nb_visits']}))

    return FeatureCollection(features)


def get_all_visits_user_geojson(user_id):
    visits = user_traces_db.load_user_all_visits_per_place(user_id)
    features = []
    for v in visits:
        features.append(Feature(geometry=Point((v['lon'], v['lat'])),
                                properties={"dur": v['dur'], "nb_visits": v['nb_visits']}))

    return FeatureCollection(features)


def export_user_data(user_id):
    import csv
    import zipfile

    # get the raw traces
    points = user_traces_db.load_all_raw_points(user_id)

    # create a temporary file
    fname = 'user_{}.json'.format(user_id)
    zipfname = 'user_traces.zip'
    with open(fname, 'w') as f:
        json.dump(points, f)

    # zip the file
    with zipfile.ZipFile(zipfname, 'w', zipfile.ZIP_DEFLATED) as zf:
        try:
            print('adding file %s' % fname)
            zf.write(fname)
        finally:
            print('closing')
            zf.close()
    return zipfname


def autocomplete_location(user_id, location, query):    
    p = ThreadPool(3)

    # get the current address
    res_address = p.apply_async(utils.get_address, args=(location, ))
    # get the user locations
    res_user_places = p.apply_async(user_traces_db.autocomplete_location, args=(user_id, location, query, 250, 5))
    # get the foursquare places
    res_foursquare_places = p.apply_async(foursquare.autocomplete_location, args=(location, query, 500, 10))

    p.close()
    p.join()

    street, city = res_address.get()
    user_places = res_user_places.get()
    foursquare_places = res_foursquare_places.get()

    res = {
        'street': street,
        'city': city,
        'places': []
    }

    res['places'] += user_places

    # filter the venue ids to remove the ones that appear in the user places
    venue_ids = set(p['venueid'] for p in user_places if p['venueid'] != "")
    res['places'] += [p for p in foursquare_places if p['venueid'] not in venue_ids]

    # return all the "relevant" places
    return res


def all_places(user_id, location, distance):
    # get the current address
    street, city = utils.get_address(location)
    res = {
        'street': street,
        'city': city,
        'places': []
    }

    # get all user places
    user_places = user_traces_db.get_all_user_places(user_id, location, distance)
    for place in user_places:
        res['places'].append({
            "name": place['name'],
            "venueid": place['venue_id'],
            "placeid": place['place_id'],
            "category": place['category'] if place['category'] else "",
            "city": place['city'],
            "score": place.get('sml', 1.0),
            "address": place['address'],
            "latitude": place['latitude'],
            "longitude": place['longitude'],
            "checkins": 0,
            "distance": place['distance'],
            "origin": "user",
            "emoji": place['emoji'],
            "icon": place['icon']
        })

    # filter the venue ids
    venue_ids = set(p['venueid'] for p in user_places if p['venueid'] != "")

    # get all foursquare places
    foursquare_places = foursquare.get_all_places_from_db(location, distance=250)

    for place in [p for p in foursquare_places if p['venueid'] not in venue_ids]:
        category = place['categories'][0] if len(place['categories']) > 0 else ""
        res['places'].append({
            "name": place['name'],
            "venueid": place['venue_id'],
            "placeid": "",
            "category": category,
            "city": place['city'],
            "address": place['address'],
            "latitude": place['latitude'],
            "longitude": place['longitude'],
            "checkins": place['nb_checkins'],
            "distance": place['distance'],
            "origin": "foursquare"
        })

    return res


def closest_place(user_id, location):
    # get the user places
    user_places = user_traces_db.autocomplete_location(user_id, location, "", distance=100, limit=5)
    if user_places:
        return user_places[0]

    # get the nearby foursquare places
    foursquare_places = foursquare.autocomplete_location(location, "", distance=250, limit=5)
    if foursquare_places:
        return foursquare_places[0]

    return None


def autocomplete_personal_information(user_id, category):
    fname = 'supp/personal_information_all.csv'
    pis = {}
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(';')  # header
        for line in f:
            fields = dict(zip(header, line.rstrip().split(';')))
            picid = fields['picid']
            pi = fields['personal_information']
            icon = fields['icon']

            if picid not in pis:
                pis[picid] = []
            pis[picid].append({
                "picid": picid,
                "pi": pi,
                "icon": icon
            })

    return pis


def add_personal_information(pi):
    print("adding personal information: %s" % pi)
    user_id = pi['user_id']

    # save the personal information to the database
    pi_id = user_traces_db.save_user_personal_information_to_db(pi)
    pi['pi_id'] = pi_id

    # Create the corresponding aggregated personal information
    api_id = user_traces_db.create_or_update_aggregate_personal_information(user_id, pi, pi_id)

    # get the user update
    user_update = get_user_personal_information_update_from_db(user_id, pi_id, api_id)
    print(user_update)
    return user_update


def update_personal_information(pi):
    print("update personal information: %s" % pi)
    user_traces_db.update_user_aggregated_personal_information(pi)

    return {}


def register_user(type, date, uuid, push_notification_id):
    user = {
        "push_notification_id": push_notification_id,
        "date_added": date
    }
    if type == 'ios':
        user['ios_id'] = uuid
    elif type == 'android':
        user['android_id'] = uuid

    user_id = user_traces_db.save_user_info_to_db(user)
    return user_id


def update_user_information(user_id, type, uuid, push_notification_id):
    user = {
        "push_notification_id": push_notification_id,
        "user_id": user_id
    }
    if type == 'ios':
        user['ios_id'] = uuid
    elif type == 'android':
        user['android_id'] = uuid

    user_traces_db.update_user_info_in_db(user)


def update_user_info(user_id, type, date, uuid, push_notification_id):
    user = {
        "push_notification_id": push_notification_id,
        "date_added": date,
        "user_id": user_id
    }
    if type == 'ios':
        user['ios_id'] = uuid
    elif type == 'android':
        user['android_id'] = uuid

    user_traces_db.update_user_info(user)


def get_day_user_update_from_db(user_id, days):
    user_update = {
        "uid": user_id,
        "days": days,
        "p": [],  # places
        "v": [],  # visits
        "m": [],  # moves
        "pi": []  # personal information
    }

    for day in days:
        user_update['p'] += user_traces_db.load_user_places(user_id, day)
        user_update['v'] += user_traces_db.load_user_visits(user_id, day)
        user_update['m'] += user_traces_db.load_user_moves(user_id, day)

    place_ids = [e['pid'] for e in user_update['p']]

    for place_id in place_ids:
        pi = user_traces_db.load_user_personal_information(user_id, place_id)
        user_update['pi'] += pi

    if len(user_update['v']) > 0:
        user_update['from'] = user_update['v'][0]['a']
        user_update['to'] = user_update['v'][-1]['d']
    else:
        user_update['from'] = 0
        user_update['to'] = 0

    return user_update


def get_visit_user_update_from_db(user_id, visit_id, day):
    user_update = {
        "uid": user_id,
        "days": [day],
        "p": [],    # places
        "v": [],    # visits
        "m": [],    # moves
        "pi": []   # personal information
    }

    visit = user_traces_db.load_user_visit(user_id, visit_id)
    place_id = visit['pid']
    place = user_traces_db.load_user_place(user_id, place_id)

    user_update['p'] = [place]
    user_update['v'] = [visit]

    pi = user_traces_db.load_user_personal_information(user_id, place_id)
    user_update['pi'] = pi

    if len(user_update['v']) > 0:
        user_update['from'] = user_update['v'][0]['a']
        user_update['to'] = user_update['v'][-1]['d']
    else:
        user_update['from'] = 0
        user_update['to'] = 0

    return user_update


def get_user_personal_information_update_from_db(user_id, pi_id, api_id):
    user_update = {
        "uid": user_id,
        "pi": [],
        "api": []
    }

    # add personal information
    pi = user_traces_db.load_user_personal_information_from_id(user_id, pi_id)
    user_update['pi'] = [pi]

    # create or update aggregated personal information
    api = user_traces_db.load_user_aggregated_personal_information_from_id(user_id, api_id)
    user_update['api'] = [api]

    return user_update


def get_user_review_challenge_from_db(user_id, day):
    return user_traces_db.load_user_review_challenge(user_id, day)


def update_user_review_challenge_from_db(user_id, review_challenges):
    for rcid, date_completed in review_challenges.items():
        challenge = {
            "user_id": user_id,
            "review_challenge_id": rcid,
            "date_completed": date_completed
        }
        user_traces_db.update_user_challenge(challenge)
        print("updated rc %s with %s" % (rcid, challenge))


def get_personal_information_categories():
    fname = 'supp/personal_information_categories.csv'
    pics = []
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(';')  # header
        for line in f:
            fields = dict(zip(header, line.rstrip().split(';')))
            pics.append({
                "picid": fields['acronym'],
                "name": fields['name'],
                "detail": fields['description'],
                "explanation": fields['explanation'],
                "icon": fields['icon'],
                "question": fields['question'],
                "scale": fields['scale'].split(',')
            })

    return pics


def get_recording_places():
    fname = 'supp/recording_places.csv'
    places = []
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(',')  # header
        for line in f:
            fields = dict(zip(header, line.rstrip().split(',')))
            places.append({
                "placeid": fields['PlaceID'],
                "placetype": fields['Category'],
                "typeid": fields['Type'],
                "name": fields['Location'],
                "icon": fields['icon'],
                "longitude": float(fields['Longitude']),
                "latitude": float(fields['Latitude'])
            })

    return places


def get_aggregated_personal_information(user_id):
    res = user_traces_db.load_user_aggregated_personal_information(user_id)
    for pi in res:
        pi['piid'] = str(pi['piid'])
        pi_ids = pi['piids']
        pi_ids_str = []
        for pi_id in pi_ids:
            pi_ids_str.append(str(pi_id))
        pi['piids'] = pi_ids_str
    return res


def save_aggregated_personal_information_reviews(user_id, reviews):
    for pi_id, review in reviews.items():
        pi = {
            'user_id': user_id,
            'pi_id': pi_id,
            'review_personal_information': review[0],
            'review_explanation': review[1],
            'review_privacy': review[2],
            'reviewed': True
        }
        print(pi)
        user_traces_db.update_user_aggregated_personal_information(pi)
    return {}


def get_raw_trace(user_id, start, end, type=None, utc=False):
    raw_traces = user_traces_db.get_raw_trace(user_id, start, end, utc)
    if type == 'geojson':
        features = []
        for t in raw_traces:
            features.append(Feature(geometry=Point((t['lat'], t['lon'])),
                                    properties={"ts": t['ts'], "label": utils.hm(t['ts'])}))
        return FeatureCollection(features)
    else:
        return raw_traces


def get_raw_visits(user_id, day, type=None):
    raw_visits = user_traces_db.load_user_all_visits_on_day(user_id, day)
    if type == 'geojson':
        features = []
        for t in raw_visits:
            features.append(Feature(geometry=Point((t['lon'], t['lat'])),
                                    properties={"dur": t['dur'], "label": t['name']}))
        return FeatureCollection(features)
    else:
        return raw_visits


def get_consent_form():
    fname = 'supp/consent_form.csv'
    form = []
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(";")
        for line in f:
            fields = dict(zip(header, line.rstrip().split(";")))
            form.append(fields["Description"])
    return form


def get_text(fname):
    text = []
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(";")
        for line in f:
            fields = dict(zip(header, line.rstrip().split(";")))
            text.append(fields)
    return text


def update_reviews(reviews, user_id):
    for review_id, answer in reviews.items():
        pi = {
            "user_id": user_id,
            "pi_id": review_id,
            "rating": answer
        }
        print(pi)

        user_traces_db.update_user_personal_information(pi)


def add_visit(visit_update):
    user_id = visit_update['user_id']
    place_id = visit_update['new_place_id']
    venue_id = visit_update['venue_id']
    name = visit_update['name']
    city = visit_update['city']
    address = visit_update['address']
    day = visit_update['day']

    arrival = visit_update['arrival']      # UTC time
    departure = visit_update['departure']  # UTC time

    print("arrival: %s, departure: %s" % (arrival, departure))

    visit = {
        "user_id": user_id,
        "latitude": visit_update['lat'],
        "longitude": visit_update['lon'],
        "arrival": arrival,
        "departure": departure,
        "arrival_utc_offset": user_traces_db.get_utc_offset_for_visit_time(user_id, day, arrival),
        "departure_utc_offset": user_traces_db.get_utc_offset_for_visit_time(user_id, day, departure),
        "original_arrival": arrival,
        "added_by_user": True,
        "day": day
    }

    place = {
        "latitude": visit_update['lat'],
        "longitude": visit_update['lon'],
        "user_id": user_id
    }

    if venue_id == '' and place_id == '':  # user-generated place
        # add the place to the database
        place['name'] = name
        place['city'] = city
        place['address'] = address
        place['color'] = utils.pick_place_color('home')
        place_id = user_traces_db.save_user_place_to_db(place)

        # save the visit to the database
        visit['place_id'] = place_id
        visit_id = add_visit_in_db(visit)

        # optional: get personal information about this place
        user_update = get_visit_user_update_from_db(user_id, visit_id, day)
        print("add place 0")
        print(user_update)
        return user_update

    elif venue_id != '':  # foursquare place
        # get the place from foursquare
        place_id = save_foursquare_venue_in_db(venue_id, place)

        visit['place_id'] = place_id
        visit_id = add_visit_in_db(visit)

        user_update = get_visit_user_update_from_db(user_id, visit_id, day)
        print("user update 1")
        print(user_update)
        return user_update

    elif place_id != '':  # already-existing user place
        # add the visit to the database
        visit['place_id'] = place_id
        visit_id = add_visit_in_db(visit)

        user_update = get_visit_user_update_from_db(user_id, visit_id, day)
        print("add place 2")
        print(user_update)
        return user_update


def update_visit(visit_update):
    user_id = visit_update['user_id']
    old_place_id = visit_update['old_place_id']
    new_place_id = visit_update['new_place_id']
    visit_id = visit_update['visit_id']
    new_venue_id = visit_update['venue_id']
    name = visit_update['name']
    city = visit_update['city']
    address = visit_update['address']
    day = visit_update['day']

    arrival = visit_update['arrival']
    departure = visit_update['departure']

    # getting the venue id of the old place
    user_place = user_traces_db.load_user_place(user_id, old_place_id)
    print(user_place)
    old_venue_id = user_place.get('vid', '')
    visit = {
        "user_id": user_id,
        "visit_id": visit_id,
        "day": day,
        "latitude": visit_update['lat'],
        "longitude": visit_update['lon'],
        "arrival": arrival,
        "departure": departure,
        "arrival_utc_offset": user_traces_db.get_utc_offset_for_visit_time(user_id, day, arrival),
        "departure_utc_offset": user_traces_db.get_utc_offset_for_visit_time(user_id, day, departure)
    }

    place = {
        "user_id": user_id,
        "latitude": visit_update['lat'],
        "longitude": visit_update['lon']
    }

    if user_place and user_place['name'] == name:
        # only update the visit
        visit_id = update_visit_in_db(visit)

        # update the user place with the new longitude and latitude
        place['place_id'] = old_place_id
        user_traces_db.update_user_place(place)

        # TODO: add personal information inference (only if home...)
        user_update = get_visit_user_update_from_db(user_id, visit_id, day)
        print("user update 0")
        print(user_update)
        return user_update
    else:
        if new_venue_id == "" and old_venue_id == "" and new_place_id == "":
            # the user changed the name and address of the place that was not a FSQ venue
            place['name'] = name
            place['city'] = city
            place['address'] = address
            place['place_id'] = old_place_id
            user_traces_db.update_user_place(place)
            # do we need to get new personal information about the place?

            # update the visit
            visit_id = update_visit_in_db(visit)

            user_update = get_visit_user_update_from_db(user_id, visit_id, day)
            print("user update 1")
            print(user_update)
            return user_update

        elif new_venue_id != "":
            # the user selected a new foursquare place
            place_id = save_foursquare_venue_in_db(new_venue_id, place)

            visit['place_id'] = place_id
            visit_id = update_visit_in_db(visit)

            print(user_id, visit_id, day)

            user_update = get_visit_user_update_from_db(user_id, visit_id, day)
            print("user update 2")
            print(user_update)
            return user_update

        elif new_place_id != "":
            # the user selected another place in the users/places database
            # update the visit
            visit['place_id'] = new_place_id
            visit_id = update_visit_in_db(visit)

            user_update = get_visit_user_update_from_db(user_id, visit_id, day)
            print("user update 3")
            print(user_update)
            return user_update
        elif old_venue_id != "" and new_venue_id == "" and new_place_id == "":
            # the user changed a foursquare place to a custom place
            # create a new place
            place['name'] = name
            place['city'] = city
            place['address'] = address
            place['color'] = utils.pick_place_color('home')
            place['type'] = 'home'
            place['emoji'] = '👣'
            place['icon'] = 'map-marker'
            place_id = user_traces_db.save_user_place_to_db(place)

            if name.lower() == 'home':
                place['emoji'] = '🏠'
                place['icon'] = 'home'

            # update the visit
            visit['place_id'] = place_id
            visit_id = add_visit_in_db(visit)

            # optional: get personal information about this place

            user_update = get_visit_user_update_from_db(user_id, visit_id, day)
            print("user update 4")
            print(user_update)
            return user_update

    print("Nothing to do")
    return {}


def save_foursquare_venue_in_db(venue_id, place):
    user_id = place['user_id']
    result = foursquare.get_place(venue_id)

    place['name'] = result['name']
    place['category'] = result['category'][0]
    place['longitude'] = result['location']['lon']
    place['latitude'] = result['location']['lat']
    place['city'] = result['location']['city']
    place['address'] = result['location']['address']
    place['venue_id'] = result['id']
    place['type'] = 'place'
    place['color'] = utils.pick_place_color(place['name'])
    place['emoji'] = result['emoji']
    place['icon'] = result['icon']

    # save the new place to the database
    place_id = user_traces_db.save_user_place_to_db(place)
    place['place_id'] = place_id

    # get the personal information about the new place
    res_pi = personal_information.get_personal_information(venue_id)

    # get the reviews associated to the new new personal information
    for c, v in res_pi.items():
        for pi in v:
            pi['user_id'] = user_id
            pi['place_id'] = place_id
            pi['category_id'] = c
            pi['source'] = list(pi['source'])

            pi_id = user_traces_db.save_user_personal_information_to_db(pi)
            pi['pi_id'] = pi_id

            user_traces_db.create_or_update_aggregate_personal_information(user_id, pi, pi_id)

    return place_id


def update_visit_in_db(visit):
    visit_id = visit['visit_id']
    visit['visited'] = True

    # update the visit
    user_traces_db.update_user_visit(visit)

    return visit_id


def add_visit_in_db(visit):
    # add the visit to the database
    visit['visited'] = True
    visit_id = user_traces_db.save_user_visit_to_db(visit)

    return visit_id


def delete_visit(visit_update):
    user_traces_db.delete_user_visit(visit_update['user_id'], visit_update['visit_id'])
    return {}


def update_visit_visited(visit_update):
    user_traces_db.update_visit_visited(visit_update['user_id'], visit_update['visit_id'])
    return {}


def update_place_type(place_update):
    place_type = place_update['place_type']
    user_id = place_update['user_id']
    place_id = place_update['place_id']

    place = {
        'user_id': user_id,
        'place_id': place_id,
        'place_type': place_type
    }

    if place_type == 2:  # home confirmed
        place['name'] = "Home"
        place['venue_id'] = ''
        place['emoji'] = '🏠'
        place['icon'] = 'home'

    elif place_type == 0:  # wrong inference
        place['place_type'] = -1

    user_traces_db.update_user_place(place)

    user_update = {
        "p": [user_traces_db.load_user_place(user_id, place_id)]
    }

    print(user_update)
    return user_update


def update_place(place_update):
    user_traces_db.update_user_place(place_update)

    user_update = {
        "p": [user_traces_db.load_user_place(place_update['user_id'], place_update['place_id'])]
    }

    print(user_update)
    return user_update


def send_incoming_message_to_queue(filename):
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
    channel = connection.channel()

    channel.queue_declare(queue='incoming_queue', durable=True)

    channel.basic_publish(exchange='',
                          routing_key='incoming_queue',
                          body=filename,
                          properties=pika.BasicProperties(
                              delivery_mode=2,  # make message persistent
                          ))
    connection.close()


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print("Error - you should choose an argument:")
        base = sys.argv[0]
        print('\t{} user user_id day (yyyy-mm-dd)'.format(base))
        sys.exit(0)

    arg = sys.argv[1]
    if arg == 'user':
        if len(sys.argv) != 4:
            print("Error - you should provide a valid user id and day (yyyy-mm-dd)")
            sys.exit(0)

        user_id = sys.argv[2]
        day = sys.argv[3]
        user_update = get_user_update_from_db(user_id, day)
        print(user_update)
    elif arg == 'pi-cat':
        cat = get_personal_information_categories()
        print(cat)
    elif arg == 'trace':
        if len(sys.argv) != 5:
            print("Error - you should provide a valid user id, start and end timestamps")
            sys.exit(0)

        user_id = sys.argv[2]
        start = sys.argv[3]
        end = sys.argv[4]
        trace = get_raw_trace(user_id, start, end)
        print(trace)
    elif arg == 'consent-form':
        print(get_consent_form())

    elif arg == 'autocomplete':
        if len(sys.argv) != 6:
            print("Error - you should provide a valid user id, lon, lat and query")
            sys.exit(0)

        user_id = sys.argv[2]
        lon = float(sys.argv[3])
        lat = float(sys.argv[4])
        query = sys.argv[5]

        location = {"lon": lon, "lat": lat}
        res = autocomplete_location(user_id, location, query)

        print(res)

    else:
        print("Error - specify an argument")
        sys.exit(0)
