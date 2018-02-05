import sys
import time
import user_traces_db


def get_user_update_from_db(user_id, day):
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

    user_update['pi'] = []
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


def get_user_review_challenge_from_db(user_id, day):
    return user_traces_db.load_user_review_challenge(user_id, day)


def get_personal_information_categories():
    fname = 'scripts/personal_information_categories.csv'
    pics = []
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(';')  # header
        for line in f:
            fields = dict(zip(header, line.rstrip().split(';')))
            pics.append({
                "picid": fields['acronym'],
                "name": fields['name'],
                "desc": fields['description'],
                "explanation": fields['explanation'],
                "icon": fields['icon']
            })

    return pics


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

    else:
        print("Error - specify an argument")
        sys.exit(0)



