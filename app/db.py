import sys
import time
import user_traces_db
import personal_information
import foursquare
import utils


def get_day_user_update_from_db(user_id, day):
    user_update = {
        "uid": user_id,
        "day": day,
        "rv": [],    # reviews for visits
        "rpi": [],   # reviews for personal information
        "p": [],     # places
        "v": [],     # visits
        "m": [],     # moves
        "pi": [],    # personal information
        "q": []      # questions
    }

    user_update['p'] = user_traces_db.load_user_places(user_id, day)
    user_update['v'] = user_traces_db.load_user_visits(user_id, day)
    user_update['m'] = user_traces_db.load_user_moves(user_id, day)

    place_ids = [e['pid'] for e in user_update['p']]
    visit_ids = [e['vid'] for e in user_update['v']]

    for place_id in place_ids:
        pi = user_traces_db.load_user_personal_information(user_id, place_id)
        user_update['pi'] += pi

    pi_ids = [e['piid'] for e in user_update['pi']]
    questions = set()
    for pi_id in pi_ids:
        r = user_traces_db.load_user_review_pi(user_id, pi_id)
        for e in r:
            questions.add(e['q'])
        user_update['rpi'] += r

    for visit_id in visit_ids:
        r = user_traces_db.load_user_review_visit(user_id, visit_id)
        for e in r:
            questions.add(e['q'])
        user_update['rv'] += r

    user_update['q'] = list(questions)

    for r in user_update['rv']:
        idx = user_update['q'].index(r['q'])
        r['q'] = idx

    for r in user_update['rpi']:
        idx = user_update['q'].index(r['q'])
        r['q'] = idx

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
        "day": day,
        "rv": [],  # reviews for visits
        "rpi": [],  # reviews for personal information
        "p": [],  # places
        "v": [],  # visits
        "m": [],  # moves
        "pi": [],  # personal information
        "q": []  # questions
    }

    visit = user_traces_db.load_user_visit(user_id, visit_id)
    place_id = visit['pid']
    place = user_traces_db.load_user_place(user_id, place_id)

    user_update['p'] = [place]
    user_update['v'] = [visit]

    pi = user_traces_db.load_user_personal_information(user_id, place_id)
    user_update['pi'] = pi

    pi_ids = [e['piid'] for e in user_update['pi']]
    questions = set()
    for pi_id in pi_ids:
        r = user_traces_db.load_user_review_pi(user_id, pi_id)
        for e in r:
            questions.add(e['q'])
        user_update['rpi'] += r

    r = user_traces_db.load_user_review_visit(user_id, visit_id)
    for e in r:
        questions.add(e['q'])
    user_update['rv'] += r

    user_update['q'] = list(questions)

    for r in user_update['rv']:
        idx = user_update['q'].index(r['q'])
        r['q'] = idx

    for r in user_update['rpi']:
        idx = user_update['q'].index(r['q'])
        r['q'] = idx

    if len(user_update['v']) > 0:
        user_update['from'] = user_update['v'][0]['a']
        user_update['to'] = user_update['v'][-1]['d']
    else:
        user_update['from'] = 0
        user_update['to'] = 0

    return user_update


def get_user_review_challenge_from_db(user_id, day):
    return user_traces_db.load_user_review_challenge(user_id, day)


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
                "icon": fields['icon']
            })

    return pics


def get_raw_trace(user_id, start, end):
    return user_traces_db.get_raw_trace(user_id, start, end)


def get_consent_form():
    fname = 'supp/consent_form.csv'
    form = []
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(";")
        for line in f:
            fields = dict(zip(header, line.rstrip().split(";")))
            form.append(fields["Description"])
    return form


def add_visit(visit_update):
    user_id = visit_update['user_id']
    place_id = visit_update['new_place_id']
    venue_id = visit_update['venue_id']
    name = visit_update['name']
    city = visit_update['city']
    address = visit_update['address']
    day = visit_update['day']

    visit = {
        "user_id": user_id,
        "latitude": visit_update['lat'],
        "longitude": visit_update['lon'],
        "arrival": visit_update['arrival'],
        "departure": visit_update['departure'],
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

        # update the visit
        visit['place_id'] = place_id
        visit_id = user_traces_db.save_user_visit_to_db(visit)

        # optional: get personal information about this place

        user_update = {
            "day": day,
            "p": [user_traces_db.load_user_place(user_id, place_id)],
            "v": [user_traces_db.load_user_visit(user_id, visit_id)]
        }
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
        visit_id = user_traces_db.save_user_visit_to_db(visit)

        user_update = {
            "day": day,
            "v": [user_traces_db.load_user_visit(user_id, visit_id)]
        }
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

    # getting the venue id of the old place
    user_place = user_traces_db.load_user_place(user_id, old_place_id)
    print(user_place)
    old_venue_id = user_place['vid']
    visit = {
        "user_id": user_id,
        "visit_id": visit_id,
        "latitude": visit_update['lat'],
        "longitude": visit_update['lon'],
        "arrival": visit_update['arrival'],
        "departure": visit_update['departure']
    }

    place = {
        "user_id": user_id,
        "latitude": visit_update['lat'],
        "longitude": visit_update['lon']
    }

    if user_place['name'] == name:
        # only update the visit
        user_traces_db.update_user_visit(visit)

        # update the user place with the new longitude and latitude
        place['place_id'] = old_place_id
        user_traces_db.update_user_place(place)

        # TODO: add personal information inference (only if home...)
        user_update = {
            "day": day,
            "p": [user_traces_db.load_user_place(user_id, old_place_id)],
            "v": [user_traces_db.load_user_visit(user_id, visit_id)]
        }
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
            user_traces_db.update_user_visit(visit)

            user_update = {
                "day": day,
                "p": [user_traces_db.load_user_place(user_id, old_place_id)],
                "v": [user_traces_db.load_user_visit(user_id, visit_id)]
            }
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
            user_traces_db.update_user_visit(visit)

            user_visit = user_traces_db.load_user_visit(user_id, visit_id)
            user_update = {
                "day": day,
                "v": [user_visit]
            }
            print("user update 3")
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

            # create the set of reviews for the personal information
            for review in personal_information.create_reviews_for_personal_information(pi):
                _ = user_traces_db.save_user_reviews_to_db(review)

    return place_id


def update_visit_in_db(visit):
    user_id = visit['user_id']
    visit_id = visit['visit_id']

    # update the visit
    user_traces_db.update_user_visit(visit)

    # update the review associated to the visit to mark it as "yes" (1)
    review = {
        "answer": 1,
        "user_id": user_id,
        "visit_id": visit_id
    }
    user_traces_db.update_user_review_visit(review)

    return visit_id


def add_visit_in_db(visit):
    # add the visit to the database
    visit_id = user_traces_db.save_user_visit_to_db(visit)

    # add the review associated to the visit to mark it as "yes" (1)
    visit['visit_id'] = visit_id
    review = personal_information.create_reviews_for_visit(visit)
    review['answer'] = 1
    user_traces_db.save_user_reviews_to_db(review)

    return visit_id


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

    else:
        print("Error - specify an argument")
        sys.exit(0)



