import user_traces_db

def get_user_update_from_db(user_id, day):
    user_update = {
        "userid": user_id,
        "day": day,
        "moves": [],
        "places": [],
        "visits": []
    }

    user_update['places'] = user_traces_db.load_user_places(user_id, day)
    user_update['visits'] = user_traces_db.load_user_visits(user_id, day)
    user_update['moves'] = user_traces_db.load_user_moves(user_id, day)

    if len(user_update['visits']) > 0:
        user_update['from'] = user_update['visits'][0]['arrival']
        user_update['to'] = user_update['visits'][-1]['departure']
    else:
        user_update['from'] = 0
        user_update['to'] = 0
    return user_update
