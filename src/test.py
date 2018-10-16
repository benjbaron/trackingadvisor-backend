from psycopg2 import sql
import psycopg2
import time

import foursquare
import utils


def get_relevance_ratings(place_id, connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query = sql.SQL("""SELECT pi_id, array_agg(rating) as ratings
               FROM place_personal_information_relevance
               WHERE place_id = %s
               GROUP BY pi_id;""")

    data = (place_id,)
    cursor.execute(query, data)
    return dict([(record['pi_id'], dict(record)) for record in cursor])


def get_all_distinct_place_ids(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("SELECT DISTINCT place_id FROM places;")
    cursor.execute(query_string)
    return [record['place_id'] for record in cursor]


if __name__ == '__main__':
    print("hello")
    start_time = time.time()
    c_study, cur_study = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)
    c_fsq, cur_fsq = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    print("1 - %s" % (time.time() - start_time))

    models = {}

    start_time = time.time()
    place_ids = get_all_distinct_place_ids(c_study, cur_study)
    print("got %s place ids" % len(place_ids))

    for place_id in place_ids:
        # 1 - get the personal information relevance information
        ratings = get_relevance_ratings(place_id, connection=c_study, cursor=cur_study)

        # 2 - get the personal information computed by the models for this place
        start_time = time.time()
        pis = foursquare.get_place_personal_information_from_db(place_id, connection=c_fsq, cursor=cur_fsq)

        # 3 - aggregate per model
        # a model is defined by (model_type, feature_type, avg, phrase_modeler)
        for pi in pis:
            pi_id = pi['pi_id']
            rank = pi['rank']
            model = (pi['model_type'], pi['feature_type'], pi['avg'], pi['phrase_modeler'])

            if model not in models:
                models[model] = [[0]*5 for _ in range(10)]
                # for _ in range(10):
                #     models[model].append([0]*5)

            rating = [] if pi_id not in ratings else ratings[pi_id]['ratings']
            for r in rating:
                models[model][rank][r-1] += 1

    print("end - %s" % (time.time() - start_time))

    # print the models
    print("models: %s" % len(models))
    for model in models.keys():
        ranks = models[model]
        print(model)
        for rank, r in enumerate(ranks):
            print("\t", rank, r)
