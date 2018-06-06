import os, sys
import re
import difflib
from collections import OrderedDict
import nltk
from nltk.corpus import wordnet as wn
import string
import psycopg2
import psycopg2.extras
from multiprocessing import Pool, Manager
import itertools

import dbpedia
import foursquare
import user_traces_db
import utils

nltk.download('punkt', quiet=True)


PREPOSITIONS = {'of', 'in', 'at', 'on'}
ARTICLES = {'a', 'an', 'of', 'the', 'is', 'and', 'at', 'in', 'on', 'yes'}
PATH = "supp/"
ROOTS_PATH = PATH + 'dbpedia_type_roots.txt'


def title_except(s, exceptions=ARTICLES):
    if s == 'YES':
        return s

    word_list = re.split(" ", s)       # re.split behaves as expected
    final = [word_list[0].capitalize()]
    for word in word_list[1:]:
        final.append(word if word in exceptions else word.capitalize())
    return " ".join(final)


def get_tokens(text):
    lowers = text.lower()
    no_punctuation = lowers.translate(lowers.maketrans('', '', string.punctuation))
    tokens = nltk.word_tokenize(no_punctuation)
    return tokens


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def has_numbers(s):
    return any(char.isdigit() for char in s)


def are_similar(s1, s2):
    seq = difflib.SequenceMatcher(a=s1, b=s2)
    ratio = seq.ratio()
    return ratio >= 0.75


def similarity(s1, s2, type_roots):
    seq = difflib.SequenceMatcher(a=s1, b=s2)
    ratio = seq.ratio()

    if ratio >= 0.75:
        return True

    s1_tokens = set(get_tokens(s1))
    s2_tokens = set(get_tokens(s2))
    intersection = s1_tokens & s2_tokens

    s1_diff = s1_tokens - intersection - PREPOSITIONS
    s2_diff = s2_tokens - intersection - PREPOSITIONS

    if len(s1_diff) == len(s2_diff) == 1:
        if s1_diff.issubset(type_roots) and s2_diff.issubset(type_roots):
            return True

    return False


def get_dbpedia_type_roots(filepath=ROOTS_PATH):
    roots = {}
    with open(filepath, 'r') as f:
        for line in f:
            fields = line.strip().split('\t')
            uri = fields[0]
            root = fields[1]
            count = fields[2]
            if uri not in roots:
                roots[uri] = []
            roots[uri].append([root, count])
    return roots


def remove_similar_personal_information(personal_information, type, roots):
    d = OrderedDict((pi['name'], pi) for pi in personal_information)
    if type not in roots:
        return d.values()

    type_roots = set(e[0] for e in roots[type])
    for i in range(len(personal_information)-1):
        pi_1 = personal_information[i]['name']
        pi_1_tokens = set(get_tokens(pi_1))
        intersection = pi_1_tokens & type_roots
        if has_numbers(pi_1) or len(intersection) == 0:
            if pi_1 in d:
                del d[pi_1]
                continue

        for j in range(i+1, len(personal_information)):
            pi_2 = personal_information[j]['name']
            if similarity(pi_1, pi_2, type_roots):
                if pi_2 in d:
                    del d[pi_2]

    return d.values()


def get_personal_information_foursquare(venue_id):
    personal_information = {}

    # get the personal information from the venue category
    foursquare_cat = get_personal_information_categories('foursquare')
    category_place = foursquare.get_category_of_venue(venue_id)

    # TODO: add gender information
    # TODO: add price tier information (if cheap, if moderate, if expensive)

    for c in category_place:
        c_id = c['id']
        c_name = c['name']
        if c_id in foursquare_cat and foursquare_cat[c_id]:
            for k, v in foursquare_cat[c_id].items():
                if k in ['EMOJI', 'ICON']:
                    continue
                if k not in personal_information:
                    personal_information[k] = []

                if k == 'INT':
                    personal_information[k].append({
                        "source": "Foursquare",
                        "name": title_except(c_name)
                    })
                else:
                    for e in v:
                        personal_information[k].append({
                            "source": "Foursquare",
                            "name": title_except(e)
                        })

    return personal_information


def get_personal_information_dbpedia(place_id, type, roots):
    personal_information = {}

    # get the personal information categories from the place type
    dbpedia_cat = get_personal_information_categories('dbpedia')
    if type in dbpedia_cat and dbpedia_cat[type]:
        for k, v in dbpedia_cat[type].items():
            if k not in personal_information:
                personal_information[k] = []

            if k == 'INT':
                pi = dbpedia.get_place_personal_information_ids(place_id)
                filtered_pi = remove_similar_personal_information(pi, type, roots)
                for e in filtered_pi:
                    personal_information[k].append({
                        "source": "DBpedia",
                        "name": title_except(e['name'])
                    })
            else:
                for e in v:
                    if e == 'YES':
                        continue

                    personal_information[k].append({
                        "source": "DBpedia",
                        "name": title_except(e)
                    })

    return personal_information


def get_personal_information(venue_id):
    if not venue_id:
        return {}

    roots = get_dbpedia_type_roots()
    personal_information = []

    venue = foursquare.get_place_with_id(venue_id)

    # 1 - match place with DBpedia places
    place = dbpedia.get_place_with_name(venue['location'], venue['name'])
    if place:
        place_id = place['id']
        place_type = place['type']
        personal_information.append(get_personal_information_dbpedia(place_id, place_type, roots))

    # 2 - match with Foursquare places
    personal_information.append(get_personal_information_foursquare(venue['id']))
    if venue['parent_id']:
        personal_information.append(get_personal_information_foursquare(venue['parent_id']))
        parent_venue = foursquare.get_place_with_id(venue['parent_id'])
        parent_place = dbpedia.get_place_with_name(parent_venue['location'], parent_venue['name'])
        if parent_place:
            place_id = parent_place['id']
            place_type = parent_place['type']
            personal_information.append(get_personal_information_dbpedia(place_id, place_type, roots))

    # 3 - aggregate the collected personal information
    res = {}
    for pi in personal_information:
        for k, v in pi.items():
            if k not in res:
                res[k] = []
            for new_element in v:
                flag = False
                for old_element in res[k]:
                    if are_similar(new_element['name'], old_element['name']):
                        old_element['source'].add(new_element['source'])
                        flag = True
                        break
                if not flag:
                    res[k].append({'name': new_element['name'], 'source': {new_element['source']}})

    return res


def aggregate_foursquare_data():
    pass


def get_personal_information_categories(db_name):
    if db_name not in ['dbpedia', 'foursquare']:
        print("Error - database name \"{}\" is not correct".format(db_name))
        return

    categories = {}
    fname = PATH + "personal_information_{}.csv".format(db_name)
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(';')
        for line in f:
            d = dict(zip(header, line.rstrip().split(';')))
            categories[d['ID']] = dict((k,v.split(',')) for k,v in d.items() if v and k != 'ID')

    return categories


def get_personal_information_categories_detail_from_file():
    fname = PATH + 'personal_information_categories.csv'
    categories = {}
    with open(fname, 'r') as f:
        header = f.readline().rstrip().split(';')
        for line in f:
            d = dict(zip(header, line.rstrip().split(';')))
            categories[d['acronym']] = dict((k, v) for k, v in d.items() if k != 'acronym')

    return categories


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


def add_personal_information(pi):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
        INSERT INTO personal_information
        (name, category_icon, subcategory_name, subcategory_icon, category_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (name, category_id) DO UPDATE SET 
           subcategory_name=EXCLUDED.subcategory_name, name=EXCLUDED.name, subcategory_icon=EXCLUDED.subcategory_icon
        RETURNING pi_id;"""
    data = (pi.get('name', None), pi.get('category_icon', None), pi.get('subcategory_name', None),
            pi.get('subcategory_icon', None), pi.get('picid', None))

    cursor.execute(query_string, data)
    connection.commit()


def get_all_personal_information():
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
    SELECT name, category_id, pi_id
    FROM personal_information
    ORDER BY category_id ASC, name ASC;"""
    cursor.execute(query_string)
    return [dict(res) for res in cursor]


def get_personal_information_from_name_in_db(pi_name, pi_category_id):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    query_string = """
    WITH pi AS (
      SELECT %s as name, %s as category_id
    )
    SELECT p.name, p.pi_id, p.category_id, word_similarity(pi.name, p.name) as sml
    FROM personal_information p, pi
    WHERE pi.name <%% p.name AND pi.category_id = p.category_id
    ORDER BY sml DESC;"""
    data = (pi_name, pi_category_id)

    cursor.execute(query_string, data)
    res = cursor.fetchone()
    return dict(res) if res else None


def get_personal_information_from_foursquare_category(category_id):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
    SELECT c.category_id, c.name, pi.pi_id, pi.name as pi_name, pi.category_id as picid, pi.category_icon, pi.subcategory_icon, pi.subcategory_name
    FROM categories c, unnest(pi_ids) piid JOIN personal_information pi ON piid::text = pi.pi_id::text
    WHERE c.category_id = %s;"""
    cursor.execute(query_string, (category_id,))
    return [dict(res) for res in cursor]


def get_foursquare_category_topics(category_id):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
    SELECT topic_id, topic_rank, top_documents, top_words
    FROM place_category_topics
    WHERE category_id = %s
    ORDER BY topic_rank ASC;"""
    cursor.execute(query_string, (category_id,))
    return [dict(res) for res in cursor]


def get_personal_information_list_from_foursquare_category(category_id):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """SELECT pi_ids FROM categories WHERE category_id = %s"""
    cursor.execute(query_string, (category_id, ))
    res = cursor.fetchone()
    return res[0] if res and res[0] else []


def update_personal_information_in_foursquare_category(category_id, pi_ids):
    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """UPDATE categories SET pi_ids = %s WHERE category_id = %s"""
    cursor.execute(query_string, (pi_ids, category_id))
    connection.commit()


def create_or_update_foursquare_category_personal_information(category_id, pi_id):
    # get the list of personal information associated to the foursquare category
    pi_ids = get_personal_information_list_from_foursquare_category(category_id)

    # update the list if there is any update to be done
    if pi_ids and pi_id in pi_ids:
        return

    updated_pi_ids = list(set(pi_ids + [pi_id]))
    update_personal_information_in_foursquare_category(category_id, updated_pi_ids)


def remove_personal_information_from_foursquare_category(category_id, pi_id):
    # get the list of personal information associated to the foursquare category
    pi_ids = get_personal_information_list_from_foursquare_category(category_id)

    # update the list if there is any update to be done
    if pi_ids and pi_id not in pi_ids:
        return

    pi_ids.remove(pi_id)
    updated_pi_ids = list(set(pi_ids))
    update_personal_information_in_foursquare_category(category_id, updated_pi_ids)


def match_foursquare_category_to_personal_information_in_db(category_id, foursquare_cat=None):
    # get the personal information from the venue category
    if not foursquare_cat:
        foursquare_cat = get_personal_information_categories('foursquare')

    if category_id not in foursquare_cat:
        category = foursquare.get_category_info_from_id(category_id)
        print("{} ({}) not in the categories".format(category['name'], category_id))
        return

    pis = foursquare_cat[category_id]
    for picid, pi_list in pis.items():
        if picid in ['ICON', 'EMOJI']:
            continue
        for pi in pi_list:
            if pi in ['YES']:
                continue

            res = get_personal_information_from_name_in_db(pi, picid)
            if res:
                create_or_update_foursquare_category_personal_information(category_id, res['pi_id'])
            else:
                print("{} ({}) not matched".format(pi, picid))


def wrapper_match_cat_pi(t):
    cat_id, d = t
    d[cat_id] = 'running'
    match_foursquare_category_to_personal_information_in_db(cat_id)
    d[cat_id] = 'done'
    return cat_id


def match_all_foursquare_categories_to_personal_information_in_db():
    all_foursquare_categories = foursquare.get_all_categories()
    category_ids = [cat['category_id'] for cat in all_foursquare_categories]

    print("macthing the personal information of {} foursquare categories".format(len(category_ids)))

    m = Manager()
    d = m.dict()
    for cat_id in category_ids:
        d[cat_id] = 'none'

    pool = Pool(processes=5)
    result = pool.map_async(wrapper_match_cat_pi, zip(category_ids, itertools.repeat(d)))

    utils.monitor_map_progress(result, d, len(category_ids))

    result.wait()
    _ = result.get()


if __name__ == '__main__':
    base = sys.argv[0]

    if len(sys.argv) < 2:
        print("Error - specify a argument")
        print("\t{} search lon lat place-name".format(base))
        print("\t{} categories personal-information-categories-file".format(base))
        print("\t{} venue venue-id".format(base))
        sys.exit(0)

    arg = sys.argv[1]
    if arg == 'search':
        if len(sys.argv) != 5:
            print("Error - specify the correct number of arguments: lon lat place-name")
            sys.exit(0)

        lon = sys.argv[2]
        lat = sys.argv[3]
        place_name = sys.argv[4]
        location = {"lat": lat, "lon": lon}

        venue = foursquare.get_place_with_name(location, place_name)
        print("venue: {}".format(venue))

        roots = get_dbpedia_type_roots()
        personal_information = get_personal_information(venue['id'])
        print(personal_information)
    elif arg == 'categories':
        if len(sys.argv) != 3:
            print("Error - specify the database name you wish to use")
            sys.exit(0)

        db_name = sys.argv[2]
        categories = get_personal_information_categories(db_name)
        print("Done")
    elif arg == 'venue':
        if len(sys.argv) != 3:
            print("Error - specify the correct number of arguments: venue-id")
            sys.exit(0)

        venue_id = sys.argv[2]
        personal_information = get_personal_information(venue_id)
        print(personal_information)
    elif arg == 'match-fsq-pi':
        if len(sys.argv) != 3:
            print("Error - specify the correct number of arguments: category-id")
            sys.exit(0)

        category_id = sys.argv[2]
        match_foursquare_category_to_personal_information_in_db(category_id)

    elif arg == 'fsq-pi':
        if len(sys.argv) != 3:
            print("Error - specify the correct number of arguments: category-id")
            sys.exit(0)

        category_id = sys.argv[2]
        pi_ids = get_personal_information_from_foursquare_category(category_id)
        print(pi_ids)

    elif arg == 'match-all-fsq-pi':
        if len(sys.argv) != 2:
            print("Error - you have specifed the wrong number of arguments")
            sys.exit(0)

        match_all_foursquare_categories_to_personal_information_in_db()

    else:
        print("Error - specify an argument search")
        sys.exit(0)
