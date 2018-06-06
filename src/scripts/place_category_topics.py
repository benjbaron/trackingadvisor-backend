##
#
# Tutorial using NMF (Non-Negative Matrix Factorization) and LDA:
# https://medium.com/mlreview/topic-modeling-with-scikit-learn-e80d33668730.
#
# Blog post - Interpretation of topic models:
# https://towardsdatascience.com/improving-the-interpretation-of-topic-models-87fd2ee3847d
#
##

import sys
from multiprocessing import Pool, Manager
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import NMF, LatentDirichletAllocation
import numpy as np
import itertools
import time
from langdetect import detect
import psycopg2
import psycopg2.extras


DB_HOSTNAME = "colossus07"
NB_MAX_CONN = 25


def print_progress(s):
    sys.stdout.write("\r\x1b[K" + s)
    sys.stdout.flush()


def monitor_map_progress(map_result, d, total, title="Progress: "):
    while True:
        if map_result.ready():
            break
        else:
            size = sum(1 for k in d.keys() if d[k] == 'done')
            s = title + "%.2f done" % (100 * size / total)
            # s += " [%s]" % (", ".join([str(k) for k in d.keys() if d[k] == 'running']))
            print_progress(s)
            time.sleep(0.5)


def connect_to_db(database_name, cursor_type=None):
    nb_req = 0
    while nb_req < NB_MAX_CONN:
        try:
            connection = psycopg2.connect(host=DB_HOSTNAME, database=database_name, user="postgres", password="postgres")
            if cursor_type:
                cursor = connection.cursor(cursor_factory=cursor_type)
            else:
                cursor = connection.cursor()
        except psycopg2.Error as e:
            nb_req += 1
            time.sleep(random.uniform(0.1, 1.0))
        else:
            return connection, cursor

    print("Error connecting the database")
    sys.exit(0)


def get_all_category_ids():
    connection, cursor = connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
            SELECT category_id
            FROM categories;"""
    cursor.execute(query_string)
    return [r[0] for r in cursor]


def get_category_tips(category_id):
    connection, cursor = connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query_string = """
        SELECT v.venue_id, v.name, t.text as tip
        FROM venues v
        JOIN tips t ON v.venue_id = t.venue_id
        WHERE %s = ANY(v.categories)
        ORDER BY v.nb_checkins DESC;"""
    data = (category_id,)
    cursor.execute(query_string, data)
    return [dict(r) for r in cursor]


def display_topics(H, W, feature_names, documents, no_top_words, no_top_documents):
    for topic_idx, topic in enumerate(H):
        print("Topic %d:" % (topic_idx))
        print(", ".join(["%s (%.2f)" % (feature_names[i], topic[i])
                        for i in topic.argsort()[:-no_top_words - 1:-1]]))
        top_doc_indices = np.argsort( W[:,topic_idx] )[::-1][0:no_top_documents]
        for doc_index in top_doc_indices:
            print("\t%s" % documents[doc_index])


def create_documents(category_tips):
    documents = []
    for i, tip in enumerate(category_tips):
        text = tip['tip']
        try:
            lang = detect(text)
        except:
            continue

        if lang != 'en':
            continue

        documents.append(text)
    return documents


def compute_nmf(documents, nb_features=1000, nb_topics=20, debug=False):
    # NMF is able to use tf-idf
    tfidf_vectorizer = TfidfVectorizer(max_df=0.95, min_df=2, ngram_range=(1, 2), max_features=nb_features,
                                       stop_words='english')
    tfidf = tfidf_vectorizer.fit_transform(documents)
    tfidf_feature_names = tfidf_vectorizer.get_feature_names()

    if debug:
        print("tfidf shape", tfidf.shape)

    # Run NMF
    nmf_model = NMF(n_components=nb_topics, random_state=1, alpha=.1, l1_ratio=.5, init='nndsvd').fit(tfidf)
    nmf_W = nmf_model.transform(tfidf)
    nmf_H = nmf_model.components_

    return nmf_H, nmf_W, tfidf_feature_names


def compute_lda(documents, nb_features=1000, nb_topics=20, debug=False):
    # LDA can only use raw term counts for LDA because it is a probabilistic graphical model
    tf_vectorizer = CountVectorizer(max_df=0.95, min_df=2, ngram_range=(1, 2), max_features=nb_features,
                                    stop_words='english')
    tf = tf_vectorizer.fit_transform(documents)
    tf_feature_names = tf_vectorizer.get_feature_names()
    if debug:
        print("tf shape", tf.shape)

    # Run LDA
    lda_model = LatentDirichletAllocation(n_components=nb_topics, max_iter=5, learning_method='online',
                                          learning_offset=50., random_state=0).fit(tf)
    lda_W = lda_model.transform(tf)
    lda_H = lda_model.components_

    return lda_H, lda_W, tf_feature_names


def save_topics_to_database(category_id, topic_model, H, W, feature_names, documents, no_top_words, no_top_documents):
    connection, cursor = connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    for topic_idx, topic in enumerate(H):

        top_doc_indices = np.argsort(W[:, topic_idx])[::-1][0:no_top_documents]
        top_documents = [documents[doc_index] for doc_index in top_doc_indices]
        top_words = [{"words": feature_names[i], "score": topic[i]} for i in topic.argsort()[:-no_top_words - 1:-1]]

        query_string = """
            INSERT INTO place_category_topics (topic_model, topic_rank, category_id, top_documents, top_words) 
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (topic_model, category_id, topic_rank) DO 
                      UPDATE SET top_documents=EXCLUDED.top_documents, top_words=EXCLUDED.top_words;"""
        data = (topic_model, topic_idx, category_id, top_documents, psycopg2.extras.Json(top_words))

        cursor.execute(query_string, data)

    connection.commit()


def topic_model_for_category_id(category_id, topic_model='lda', nb_features=1000, nb_topics=20, nb_top_words=10, nb_top_documents=3, debug=False):
    if debug:
        print("[0] Computing models for category {}".format(category_id))

    category_tips = get_category_tips(category_id)
    if debug:
        print("[1] Retrieved {} tips for category {}".format(len(category_tips), category_id))

    if len(category_tips) < 100:
        print("category {} contains {} tips".format(category_id, len(category_tips)))
        return

    documents = create_documents(category_tips)
    if debug:
        print("[2] Created {} documents for category {}".format(len(documents), category_id))

    H = None; W = None; feature_names = None
    if topic_model == "lda":
        H, W, feature_names = compute_lda(documents, nb_features, nb_topics)
    elif topic_model == 'nmf':
        H, W, feature_names = compute_nmf(documents, nb_features, nb_topics)
    else:
        print("topic {} unknown".format(topic_model))
    if debug:
        print("[3] Computed {} model for category {}".format(topic_model, category_id))

    # display_topics(H, W, feature_names, documents, nb_top_words, nb_top_documents)
    save_topics_to_database(category_id, topic_model, H, W, feature_names, documents, nb_top_words, nb_top_documents)
    if debug:
        print("[4] Saved {} topics to database".format(nb_topics))


def wrapper_compute_topic_model(t):
    cat_id, d = t
    d[cat_id] = 'running'
    topic_model_for_category_id(cat_id)
    d[cat_id] = 'done'
    return cat_id


def compute_topic_model_for_all_categories():
    category_ids = get_all_category_ids()
    print("compute topic models for {} categories".format(len(category_ids)))

    m = Manager()
    d = m.dict()
    for cat_id in category_ids:
        d[cat_id] = 'none'

    pool = Pool(processes=5)
    result = pool.map_async(wrapper_compute_topic_model, zip(category_ids, itertools.repeat(d)))

    monitor_map_progress(result, d, len(category_ids))

    result.wait()
    _ = result.get()

    print("done")


if __name__ == '__main__':

    base = sys.argv[0]
    arg = sys.argv[1]

    if arg == 'cat' and len(sys.argv) == 8:
        category_id = sys.argv[2]
        topic_model = sys.argv[3]
        nb_features = int(sys.argv[4])
        nb_topics = int(sys.argv[5])
        nb_top_words = int(sys.argv[6])
        nb_top_documents = int(sys.argv[7])

        topic_model_for_category_id(category_id, topic_model, nb_features, nb_topics, nb_top_words, nb_top_documents)
    elif arg == 'all' and len(sys.argv) == 2:
        compute_topic_model_for_all_categories()
    else:
        print('Error - please provide the following arguments:')
        print('\t{} cat category_id topic_model nb_features nb_topics nb_top_words nb_top_documents'.format(base))
        print('\t{} all'.format(base))
        sys.exit(0)

