#!/usr/bin/env python
import sys
import pika
import time
import logging
import json
import pickle
import spacy
import heapq
import numpy
from operator import itemgetter
from spacy.lang.en.stop_words import STOP_WORDS

import nltk
from nltk.tokenize import word_tokenize
from gensim.models.phrases import Phrases, Phraser
from gensim.models import Word2Vec
from gensim.models import KeyedVectors
from gensim.models import TfidfModel
from gensim.corpora import Dictionary

import foursquare
import utils


# Define our own JSON encoder
# https://stackoverflow.com/questions/27050108/convert-numpy-type-to-python
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, numpy.integer):
            return int(obj)
        elif isinstance(obj, numpy.floating):
            return float(obj)
        elif isinstance(obj, numpy.ndarray):
            return obj.tolist()
        else:
            return super(JSONEncoder, self).default(obj)


def filter_word(word):
    """ Get the part-of-speech (pos) of the word
        List of pos: https://www.clips.uantwerpen.be/pages/mbsp-tags """
    if '_' in word:
        return False

    if word in STOP_WORDS:
        return True

    doc = nlp(word)
    if doc[0].tag_ in FILTERED_POS:
        return True

    return False


def phrase_cn(v):
    """ Determine the phrase from the array of words"""
    new_s = "_".join(v)
    if new_s in conceptnet2vec:
        return [new_s]
    else:
        return v


# load personal information tags from the database
def load_personal_information_tags_from_db(bigram=None, trigram=None, model_type='sg'):
    if model_type == 'sg':
        word2vec_wiki = wiki2vec_sg
    elif model_type == 'cbow':
        word2vec_wiki = wiki2vec_cbow
    elif model_type == 'cn':
        word2vec_wiki = conceptnet2vec

    pis_tags = {}

    for pi_id, pi in pis.items():
        picid = pi['category_id']
        if picid not in FILTERED_PICID:
            continue

        tags = [tag.split(' ') for tag in pi['tags']]

        if model_type != 'cn':
            if bigram:
                tags = [bigram[tag] for tag in tags]
            if trigram:
                tags = [trigram[tag] for tag in tags]
        else:
            if bigram is None or trigram is None:
                tags = [["_".join(tag)] if "_".join(tag) in word2vec_wiki.wv.vocab else tag for tag in tags]

        # flatten the list
        tags_list = [t for row in tags for t in row if t in word2vec_wiki.wv.vocab]
        pis_tags[pi_id] = tags_list

    return pis_tags


nltk.download('punkt')

# configure constants
RABBITMQ_HOST = 'colossus07'
RABBITMQ_QUEUE = 'rpc_study_queue'

SPACY_EN = 'data/en/en_core_web_sm/en_core_web_sm-2.0.0'

WORD2VEC_WIKI_SG = 'data/wiki/word2vec_wiki_model_all_sg'
WORD2VEC_WIKI_CBOW = 'data/wiki/word2vec_wiki_model_all_cbow'
WORD2VEC_CN = 'data/conceptnet/conceptnet2vec'

TFIDF_MODEL = 'data/tf/gensim_tfidf_venues_model'
TFIDF_DICTIONARY = 'data/tf/gensim_tfidf_venues_dictionary'

BIGRAM_MODEL = 'data/wiki/bigram_model_all'
TRIGRAM_MODEL = 'data/wiki/trigram_model_all'


# Set up the logging
logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)

# Set up the RabbitMQ channel
# Tutorial: https://www.rabbitmq.com/tutorials/tutorial-six-python.html
connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
channel = connection.channel()
channel.queue_declare(queue=RABBITMQ_QUEUE)

# load spaCy (https://spacy.io/models/)
nlp = spacy.load(SPACY_EN)
FILTERED_POS = {'JJR', 'JJS', 'RB', 'RBS', 'RBR', 'RP', 'CC', 'CD', 'DT', 'IN', 'PRP', 'UH', ','}
FILTERED_PICID = {'ADD', 'ETH', 'GEN', 'HEA', 'INT', 'REL'}

# load the trigram model from disk
logging.info('[.] loading the bigram and trigram phrase models...')
bigram = Phrases.load(BIGRAM_MODEL)
trigram = Phrases.load(TRIGRAM_MODEL)
# bigram = Phraser(bigram_model)
# trigram = Phraser(trigram_model)
logging.info('[x] done loading the bigram and trigram phrase models')

# load the tf-idf model from disk
logging.info('[.] loading the tf-idf model...')
tfidf_model = TfidfModel.load(TFIDF_MODEL)
tfidf_dictionary = Dictionary.load(TFIDF_DICTIONARY)
logging.info('[x] done loading the tf-idf model')

# load the wiki2vec_sg model from disk
logging.info('[.] loading the wiki2vec_sg model...')
wiki2vec_sg = Word2Vec.load(WORD2VEC_WIKI_SG)
wiki2vec_sg.init_sims()
logging.info('[x] loaded wiki2vec_sg with {} training epochs so far.'.format(wiki2vec_sg.epochs))

# load the wiki2vec_cbow model from disk
logging.info('[.] loading the wiki2vec_cbow model...')
wiki2vec_cbow = Word2Vec.load(WORD2VEC_WIKI_CBOW)
wiki2vec_cbow.init_sims()
logging.info('[x] loaded wiki2vec_cbow with {} training epochs so far.'.format(wiki2vec_cbow.epochs))

# load the conceptnet2vec model from disk
logging.info('[.] loading the conceptnet2vec model...')
conceptnet2vec = KeyedVectors.load(WORD2VEC_CN)
conceptnet2vec.init_sims()
logging.info('[x] loaded conceptnet2vec.')

# load the personal information tags
pis = foursquare.load_personal_information()
pis_tags_phrase_model_sg = load_personal_information_tags_from_db(bigram=bigram, trigram=trigram, model_type='sg')
pis_tags_no_phrase_model_sg = load_personal_information_tags_from_db(bigram=None, trigram=None, model_type='sg')
pis_tags_phrase_model_cbow = load_personal_information_tags_from_db(bigram=bigram, trigram=trigram, model_type='cbow')
pis_tags_no_phrase_model_cbow = load_personal_information_tags_from_db(bigram=None, trigram=None, model_type='cbow')
pis_tags_phrase_model_cn = load_personal_information_tags_from_db(bigram=bigram, trigram=trigram, model_type='cn')
pis_tags_no_phrase_model_cn = load_personal_information_tags_from_db(bigram=None, trigram=None, model_type='cn')


# Extract features from place attributes
def extract_features_from_place_tips(tips, bigram_model, trigram_model, phrase, topn=10):
    text = ' '.join(tip['text'] for tip in tips if tip['lang'] == 'en')
    text = text.lower()
    text = word_tokenize(text)

    if phrase is not None:
        text = phrase(text)
    else:
        if bigram_model:
            text = bigram_model[text]

        if trigram_model:
            text = trigram_model[text]

    vec_bow = tfidf_dictionary.doc2bow(text)
    dict_bow = dict(vec_bow)
    vec_tfidf = tfidf_model[vec_bow]

    res = []
    res_names = {}
    for w_id, s in sorted(vec_tfidf, key=lambda x: x[1], reverse=True):
        w = tfidf_dictionary[w_id]
        if filter_word(w):
            continue

        res.append([w, s, dict_bow[w_id]])
        res_names[w] = [s, dict_bow[w_id]]
        if len(res) == topn:
            break

    return res, res_names


def extract_features_from_name(name, bigram_model=None, trigram_model=None, phrase=None):
    """ Can be a place name or a category"""

    if not bigram_model and not trigram_model and not phrase:
        return word_tokenize(name.lower())

    text = word_tokenize(name.lower())
    if phrase is not None:
        return phrase(text)

    text = bigram_model[text]
    return trigram_model[text]


def extract_features_from_names(names, bigram_model, trigram_model, phrase):
    res = []
    for name in names:
        res += extract_features_from_name(name, bigram_model, trigram_model, phrase)

    return res


# Match features to interests
def match_features_to_interests(feature_names, model, pis_tags, topn=4, debug=True):
    res = {}
    for feature_name in feature_names:
        if feature_name not in model.wv.vocab:
            continue

        # go through all the interests
        pis_sim = {}
        for pi_id, tags in pis_tags.items():
            if len(tags) > 0:
                pis_sim[pi_id] = (model.wv.n_similarity([feature_name], tags), feature_name, tags)

        top = heapq.nlargest(topn, pis_sim.items(), key=lambda x: x[1][0])
        res[feature_name] = dict(top)

    return res


def match_all_features_to_interests(feature_names, model, pis_tags, topn=4, debug=True):
    # filter the features that are present in the vocabulary of the model
    feature_names = [f for f in feature_names if f in model.wv.vocab]

    if len(feature_names) == 0:
        return {}

    # go through all the interests
    pis_sim = {}
    for pi_id, tags in pis_tags.items():
        if len(tags) > 0:
            pis_sim[pi_id] = (model.wv.n_similarity(feature_names, tags), feature_names, tags)

    top = heapq.nlargest(topn, pis_sim.items(), key=lambda x: x[1][0])
    return dict(top)


# Extract interests
def get_word2vec_model_and_pis_tags(bigram, trigram, phrase, model_type):
    if model_type == 'sg':
        word2vec_wiki = wiki2vec_sg
        if bigram is None or trigram is None:
            pis_tags_wiki = pis_tags_no_phrase_model_sg
        else:
            pis_tags_wiki = pis_tags_phrase_model_sg
    elif model_type == 'cbow':
        word2vec_wiki = wiki2vec_cbow
        if bigram is None or trigram is None:
            pis_tags_wiki = pis_tags_no_phrase_model_cbow
        else:
            pis_tags_wiki = pis_tags_phrase_model_cbow
    elif model_type == 'cn':
        word2vec_wiki = conceptnet2vec
        if bigram is None and trigram is None and phrase is not None:
            pis_tags_wiki = pis_tags_phrase_model_cn
        else:
            pis_tags_wiki = pis_tags_no_phrase_model_cn
    else:
        word2vec_wiki = None
        pis_tags_wiki = None

    return word2vec_wiki, pis_tags_wiki


def get_interests_from_place_tips(place_id, place, topni=3, topnf=10, bigram=None, trigram=None, phrase=None, model_type='sg'):
    word2vec_wiki, pis_tags_wiki = get_word2vec_model_and_pis_tags(bigram, trigram, phrase, model_type)

    tips = foursquare.get_all_tips_per_venue_from_db(place_id)
    tips_features, tips_features_names = extract_features_from_place_tips(tips, bigram, trigram, phrase, topn=topnf)
    if len(tips_features_names) == 0:
        print(' [.] %s: no tip features (%s)' % (place['name'], place_id))
        return []

    phrase_model = (model_type == 'cn' and phrase is not None) or (model_type != 'cn' and bigram is not None and trigram is not None)

    feature_names = [f[0] for f in tips_features]
    matches = match_features_to_interests(feature_names, word2vec_wiki, pis_tags_wiki, topn=topni, debug=False)

    return process_multi_tips_feature_interests(matches, tips_features_names, topni=topni, t='tips', p=phrase_model, a=True, model_type=model_type)


def get_interests_from_place_name(place_id, place, topni=3, bigram=None, trigram=None, phrase=None, avg=True, model_type='sg'):
    word2vec_wiki, pis_tags_wiki = get_word2vec_model_and_pis_tags(bigram, trigram, phrase, model_type)

    place_feature_names = extract_features_from_name(place['name'], bigram, trigram, phrase)
    if len(place_feature_names) == 0:
        print(' [.] %s: no name feature (%s)' % (place['name'], place_id))
        return []

    print(" [.] get_interests_from_place_name - %s" % place_feature_names)

    phrase_model = (model_type == 'cn' and phrase is not None) or (model_type != 'cn' and bigram is not None and trigram is not None)

    if avg:
        matches = match_all_features_to_interests(place_feature_names, word2vec_wiki, pis_tags_wiki, topn=topni, debug=False)
        return process_single_feature_interests(matches, topni=topni, t='name', p=phrase_model, a=avg, model_type=model_type)
    else:
        matches = match_features_to_interests(place_feature_names, word2vec_wiki, pis_tags_wiki, topn=topni, debug=False)
        return process_multi_feature_interests(matches, topni=topni, t='name', p=phrase_model, a=avg, model_type=model_type)


def get_interests_from_place_categories(place_id, place, topni=3, bigram=None, trigram=None, phrase=None, avg=True, model_type='sg'):
    word2vec_wiki, pis_tags_wiki = get_word2vec_model_and_pis_tags(bigram, trigram, phrase, model_type)

    place_category_names = extract_features_from_names(place['category'], bigram, trigram, phrase)
    if len(place_category_names) == 0:
        print(' [.] %s: no category feature, %s (%s)' % (place['name'], place['category'], place_id))
        return []

    print(" [.] get_interests_from_place_categories - %s" % place_category_names)

    phrase_model = (model_type == 'cn' and phrase is not None) or (model_type != 'cn' and bigram is not None and trigram is not None)

    if avg:
        matches = match_all_features_to_interests(place_category_names, word2vec_wiki, pis_tags_wiki, topn=topni, debug=False)
        return process_single_feature_interests(matches, topni=topni, t='categories', p=phrase_model, a=avg, model_type=model_type)
    else:
        matches = match_features_to_interests(place_category_names, word2vec_wiki, pis_tags_wiki, topn=topni, debug=False)
        return process_multi_feature_interests(matches, topni=topni, t='categories', p=phrase_model, a=avg, model_type=model_type)


# Process resulting interests
def process_multi_tips_feature_interests(matches, features_names, topni=3, t='', p=False, a=True, model_type='sg'):
    """ Process the interests from an array of tip features
        t: feature type; p: phrase model; a: average; sg: skip-gram (CBOW) """

    res = {}
    for feature, feature_res in matches.items():
        for pi_id, (score, f_names, tags) in feature_res.items():
            if pi_id not in res:
                res[pi_id] = []
            res[pi_id].append([score, features_names[feature], f_names, tags])

    res_sorted = sorted(res.items(), key=lambda x: sum(e[0] for e in x[1])/len(x[1]), reverse=True)
    res_filtered = [(pi_id, pis[pi_id]['name'], sum(e[0] for e in score)/len(score), t, p, a, model_type, score) for pi_id, score in res_sorted]
    return res_filtered[:topni]


def process_multi_feature_interests(matches, topni=3, t='', p=False, a=True, model_type='sg'):
    """ Process the interests from an array of features
        t: feature type; p: phrase model; a: average; model_type: sg (skip-gram), cbow, cn """

    res = {}
    for feature, feature_res in matches.items():
        for pi_id, (score, f_names, tags) in feature_res.items():
            if pi_id not in res:
                res[pi_id] = []
            res[pi_id].append([score, f_names, tags])

    res_sorted = sorted(res.items(), key=lambda x: max(x[1], key=lambda y: y[0]), reverse=True)
    res_filtered = [(pi_id, pis[pi_id]['name'], max(score, key=lambda x: x[0])[0], t, p, a, model_type, score) for pi_id, score in res_sorted]
    return res_filtered[:topni]


def process_single_feature_interests(matches, topni=3, t='', p=False, a=True, model_type='sg'):
    """ Process the interests from a single feature
        t: feature type; p: phrase model; a: model_type: sg (skip-gram), cbow, cn"""

    res_sorted = sorted(matches.items(), key=lambda x: x[1], reverse=True)
    res_filtered = [(pi_id, pis[pi_id]['name'], score[0], t, p, a, model_type, score) for pi_id, score in res_sorted]
    return res_filtered[:topni]


# Get all the interests associated to a place
def get_all_interests(place_id, topni=5):
    """ This function gets all the interests of the place "place_id"
        and returns an array (possibly empty) of the different variations of the interest inference algorithm """

    place = foursquare.get_place(place_id)
    if place is None:
        return []

    print(" [.] {}  {}\n{}".format(place['emoji'], place['name'], " | ".join(c for c in place['category'])))

    # Get all the interests
    interests = [None] * 30
    # interests from place tips (phrase models)
    interests[0] = get_interests_from_place_tips(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, model_type='sg')  # Skip-Gram
    interests[10] = get_interests_from_place_tips(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, model_type='cbow')  # CBOW
    interests[20] = get_interests_from_place_tips(place_id, place, topni=topni, bigram=None, trigram=None, phrase=phrase_cn, model_type='cn')  # ConceptNet

    # interests from place tips (no phrase models)
    interests[1] = get_interests_from_place_tips(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, model_type='sg')  # Skip-Gram
    interests[11] = get_interests_from_place_tips(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, model_type='cbow')  # CBOW
    interests[21] = get_interests_from_place_tips(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, model_type='cn')  # ConceptNet

    # interests from place name (no phrase models, per-word)
    interests[2] = get_interests_from_place_name(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=False, model_type='sg')  # Skip-Gram
    interests[12] = get_interests_from_place_name(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=False, model_type='cbow')  # CBOW
    interests[22] = get_interests_from_place_name(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=False, model_type='cn')  # ConceptNet

    # interests from place name (no phrase models, mean)
    interests[3] = get_interests_from_place_name(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=True, model_type='sg')  # Skip-Gram
    interests[13] = get_interests_from_place_name(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=True, model_type='cbow')  # CBOW
    interests[23] = get_interests_from_place_name(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=True, model_type='cn')  # ConceptNet

    # interests from place name (phrase models, per-word)
    interests[4] = get_interests_from_place_name(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, avg=False, model_type='sg')  # Skip-Gram
    interests[14] = get_interests_from_place_name(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, avg=False, model_type='cbow')  # CBOW
    interests[24] = get_interests_from_place_name(place_id, place, topni=topni, bigram=None, trigram=None, phrase=phrase_cn, avg=False, model_type='cn')  # ConceptNet

    # interests from place name (phrase models, mean)
    interests[5] = get_interests_from_place_name(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, avg=True, model_type='sg')  # Skip-Gram
    interests[15] = get_interests_from_place_name(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, avg=True, model_type='cbow')  # CBOW
    interests[25] = get_interests_from_place_name(place_id, place, topni=topni, bigram=None, trigram=None, phrase=phrase_cn, avg=True, model_type='cn')  # ConceptNet

    # interests from place categories (no phrase models, per-word)
    interests[6] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=False, model_type='sg')  # Skip-Gram
    interests[16] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=False, model_type='cbow')  # CBOW
    interests[26] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=False, model_type='cn')  # ConceptNet

    # interests from place categories (no phrase models, mean)
    interests[7] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=True, model_type='sg')  # Skip-Gram
    interests[17] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=True, model_type='cbow')  # CBOW
    interests[27] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=None, trigram=None, phrase=None, avg=True, model_type='cn')  # ConceptNet

    # interests from place categories (phrase models, per-word)
    interests[8] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, avg=False, model_type='sg')  # Skip-Gram
    interests[18] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, avg=False, model_type='cbow')  # CBOW
    interests[28] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=None, trigram=None, phrase=phrase_cn, avg=False, model_type='cn')  # ConceptNet

    # interests from place categories (phrase models, mean)
    interests[9] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, avg=True, model_type='sg')  # Skip-Gram
    interests[19] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=bigram, trigram=trigram, phrase=None, avg=True, model_type='cbow')  # CBOW
    interests[29] = get_interests_from_place_categories(place_id, place, topni=topni, bigram=None, trigram=None, phrase=phrase_cn, avg=True, model_type='cn')  # ConceptNet

    return interests


def process_tags(t, tags):
    if isinstance(tags, list):
        if t == "tips":
            return [(e[2], e[3], e[0]) for e in tags]
        else:
            return [(e[1], e[2], e[0]) for e in tags]
    else:
        return [([tags[1]], tags[2], tags[0])]


# Save and retrieve interests from the database
def get_and_save_interests_to_db(place_id, topni=10):
    interests = get_all_interests(place_id, topni=topni)
    print(" [.] Got %s interests" % len(interests))

    if len(interests) == 0:
        return

    connection, cursor = utils.connect_to_db("foursquare")

    for idx, interest_list in enumerate(interests):
        if interest_list is None:
            print("No interests for index %s" % idx)
            continue

        for rank, interest in enumerate(interest_list):
            tags = process_tags(interest[3], interest[7])
            print(" [.] Tags: %s" % tags)
            ppi = {
                'place_id': place_id,
                'pi_id': interest[0],
                'score': float(interest[2]),
                'feature_type': interest[3],
                'phrase_modeler': interest[4],
                'avg': interest[5],
                'model_type': interest[6],
                'tags': json.dumps(tags, cls=JSONEncoder),
                'rank': int(rank)
            }

            foursquare.save_place_personal_information_to_db(ppi, cursor=cursor)
    connection.commit()
    print("Done saving interests")


def get_all_interests_from_db(place_id):
    interests = foursquare.get_place_personal_information_from_db(place_id)
    res = {}
    for ppi in interests:
        pi_id = ppi['pi_id']
        if pi_id not in res:
            res[pi_id] = []
        res[pi_id].append(ppi)
    return res


def get_aggregate_interests_from_db(place_id):
    interests = foursquare.get_place_personal_information_from_db(place_id)
    res = {}
    for ppi in interests:
        pi_id = ppi['pi_id']
        if pi_id not in res:
            res[pi_id] = {
                'pi_id': pi_id,
                'pi_name': pis[pi_id]['name'],
                'picid': pis[pi_id]['category_id'],
                'category_icon': pis[pi_id]['category_icon'],
                'meta': []
            }

        res[pi_id]['meta'].append({
            'rank': ppi['rank'],
            'score': ppi['score'],
            'tags': json.loads(ppi['tags']),
            'feature_type': ppi['feature_type'],
            'phrase_modeler': ppi['phrase_modeler'],
            'avg': ppi['avg'],
            'model_type': ppi['model_type']})

    return list(res.values())


def on_request(ch, method, properties, body):
    logging.info(" [.] Received %r" % body)

    start_ts = int(time.time())
    place_id = body.decode("utf-8")

    if not foursquare.has_place_personal_information_in_db(place_id):
        get_and_save_interests_to_db(place_id)

    response = get_aggregate_interests_from_db(place_id)

    ch.basic_publish(exchange='',
                     routing_key=properties.reply_to,
                     properties=pika.BasicProperties(correlation_id=properties.correlation_id),
                     body=json.dumps(response))

    end_ts = int(time.time())

    logging.info("Done in %s seconds" % (end_ts - start_ts,))
    ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_qos(prefetch_count=1)
channel.basic_consume(on_request,
                      queue=RABBITMQ_QUEUE)

ts = int(time.time())
logging.info(' [x] Waiting for RPC requests...')

channel.start_consuming()
