#!/usr/bin/env python -W ignore::DeprecationWarning

import sys
import time
import csv
import mmap
import tqdm
from collections import Counter
import numpy as np
import psycopg2
from psycopg2 import sql
from sklearn.linear_model import LogisticRegression
from imblearn.over_sampling import SMOTE
from sklearn.metrics import accuracy_score
from sklearn.metrics import confusion_matrix
from sklearn.metrics import recall_score
from sklearn.metrics import precision_score
from sklearn.metrics import f1_score
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import train_test_split
from sklearn.externals import joblib
from sklearn.model_selection import KFold
from numpy.random import choice

import utils
import foursquare

MODEL_EXPORT_NAME = 'logisitic_regression.joblib'
FQS_CHECKINS_PATH = "/home/ucfabb0/enigma/data/foursquare/dataset_TIST2015/"
FQS_CHECKINS_FILTERED_POIS = FQS_CHECKINS_PATH + "dataset_TIST2015_POIs_filtered.txt"
PLACES_PERSONAL_INFORMATION = 'foursquare_places_personal_information.txt'


# Helper functions.
def get_num_lines(file_path):
    fp = open(file_path, "r+")
    buf = mmap.mmap(fp.fileno(), 0)
    lines = 0
    while buf.readline():
        lines += 1
    return lines


def get_all_foursquare_places_and_categories():
    venues_list = {}
    venues_categories = {}
    with open(FQS_CHECKINS_FILTERED_POIS, 'r', encoding="ISO-8859-1") as f:
        for line in tqdm.tqdm(f, total=get_num_lines(FQS_CHECKINS_FILTERED_POIS)):
            fields = line.strip().split('\t')
            venue_id = fields[0]
            cat = foursquare.get_category_ids_for_venue(venue_id)
            venues_list[venue_id] = cat
            if cat:
                for c in cat['categories']:
                    if c not in venues_categories:
                        venues_categories[c] = []
                    venues_categories[c].append(venue_id)

    print("[.] Got %s venues from the Foursquare checkins dataset." % (len(set(venues_list))))
    print("[.] Got %s venue categories from the Foursquare checkins dataset." % (len(set(venues_categories))))
    return venues_list, venues_categories


def get_all_foursquare_places():
    venues_list = []
    with open(FQS_CHECKINS_FILTERED_POIS, 'r', encoding="ISO-8859-1") as f:
        for line in tqdm.tqdm(f, total=get_num_lines(FQS_CHECKINS_FILTERED_POIS)):
            fields = line.strip().split('\t')
            venues_list.append(fields[0])

    print("[.] Got %s venues from the Foursquare checkins dataset." % (len(set(venues_list))))
    return venues_list


def get_all_classifiers():
    """ Returns all possible classifiers in a list. """

    connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
    query = sql.SQL("""SELECT model_type, feature_type, avg, phrase_modeler
        FROM place_personal_information
        GROUP BY model_type, feature_type, avg, phrase_modeler;""")
    cursor.execute(query)
    return [dict(r) for r in cursor]


def get_all_distinct_place_ids(connection=None, cursor=None):
    if connection is None or cursor is None:
        connection, cursor = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)

    query_string = sql.SQL("SELECT place_id FROM place_personal_information_relevance GROUP BY place_id;")
    cursor.execute(query_string)
    return [record['place_id'] for record in cursor]


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


class Classifier(object):
    def __init__(self, params, pis_ids):
        self.model_type = params['model_type']
        self.feature_type = params['feature_type']
        self.avg = params['avg']
        self.phrase_modeler = params['phrase_modeler']
        self.pis_ids = pis_ids
        self.m = len(pis_ids)
        self.connection, self.cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)
        self.y_pred = {}
        self.y_pred_rounded = {}

    def debug(self):
        return "%s %s %s %s" % (self.model_type, self.feature_type, self.avg, self.phrase_modeler)

    def idx(self):
        return self.model_type, self.feature_type, self.avg, self.phrase_modeler

    def _get_prediction(self, place_id):
        query = sql.SQL("""SELECT pi_id, rank, score
           FROM place_personal_information
           WHERE venue_id = %s AND model_type = %s AND feature_type = %s AND avg = %s AND phrase_modeler = %s;""")
        data = (place_id, self.model_type, self.feature_type, self.avg, self.phrase_modeler)
        self.cursor.execute(query, data)
        return dict([(record['pi_id'], dict(record)) for record in self.cursor])

    def predict(self, place_id):
        if place_id not in self.y_pred and place_id not in self.y_pred_rounded:
            pred = self._get_prediction(place_id)
            y = [pred[pi_id]['score'] if pi_id in pred else 0 for pi_id in self.pis_ids]
            self.y_pred_rounded[place_id] = list(map(lambda x: 1 if x >= 0.01 else 0, y))
            self.y_pred[place_id] = y
        return self.y_pred_rounded[place_id]

    def predict_topn(self, place_id, topn=5):
        """ Predict the topn first classes of the given place_id. """
        if place_id not in self.y_pred and place_id not in self.y_pred_rounded:
            self.predict(place_id)
        topn_idx = sorted(range(len(self.y_pred[place_id])), key=lambda i: self.y_pred[place_id][i], reverse=True)[
                   :topn]
        topn_list = [(idx, self.pis_ids[idx], self.y_pred[place_id][idx], self.y_pred_rounded[place_id][idx]) for idx in
                     topn_idx]
        return topn_list

    def error_topn(self, place_id, y, topn=5):
        """ Compute the empirical error between y and y_pred for the topn classes. """
        topn_y_pred = self.predict_topn(place_id, topn)
        topn_y = [(y[idx], self.pis_ids[idx], y[idx], y[idx]) for idx, _, _, _ in topn_y_pred]
        return sum(topn_y_pred[i][3] != topn_y[i][3] for i in range(topn)) / topn

    def average_precision(self, place_id, y, debug=False):
        """ Compute the average precision for the prediction made for place_id and user rating y.
            https://en.wikipedia.org/wiki/Evaluation_measures_(information_retrieval)#Average_precision. """
        if place_id not in self.y_pred and place_id not in self.y_pred_rounded:
            self.predict(place_id)

        topn_idx = sorted(range(len(self.y_pred[place_id])), key=lambda i: self.y_pred[place_id][i], reverse=True)
        relevant_items_idx = set([idx for idx in range(len(y)) if y[idx] == 1])
        tot_relevant_items = len(relevant_items_idx)
        precisions_at_k = []
        for k in range(len(y)):
            if debug:
                print("   ", k, topn_idx[k] in relevant_items_idx, tot_relevant_items, len(precisions_at_k))
            if topn_idx[k] in relevant_items_idx:
                nb_relevant_items = sum(1 for i in range(k + 1) if topn_idx[i] in relevant_items_idx)
                precisions_at_k.append(nb_relevant_items / (k + 1))

        return sum(p for p in precisions_at_k) / len(precisions_at_k)

    def similarity(self, place_id, y):
        """ Compute the similarity between y and y_pred. """
        s = 0
        count = 0
        for i in range(self.m):
            if y[i] == 0 and self.y_pred[place_id][i] == 0:
                continue
            if y[i] == self.y_pred[place_id][i]:
                s += 1
            count += 1
        return s / count if count > 0 else 0.0

    def error(self, place_id, y):
        """ Compute the empirical error between y and y_pred. """
        if place_id not in self.y_pred and place_id not in self.y_pred_rounded:
            self.predict(place_id)

        s = 0
        count = 0
        for i in range(self.m):
            if y[i] == 0 and self.y_pred[place_id][i] == 0:
                continue
            if y[i] != self.y_pred_rounded[place_id][i]:
                s += 1
            count += 1
        err = 1 / self.m * sum(1 for i in range(self.m) if y[i] != self.y_pred_rounded[place_id][i])
        err1 = s / count if count > 0 else 1.0
        return err, err1


def create_training_set_blending():
    """ Returns the training set (x_train, y_train) for the places reviewed by the users. """
    stime = time.time()
    indexes = []
    y_train = np.zeros((nb_places * nb_pis,))
    x_train = np.zeros((nb_places * nb_pis, nb_clfs))
    for i, place_id in enumerate(place_ids):
        # 1. Get the relevance ratings for the place (y).
        ratings = get_relevance_ratings(place_id, connection=c_study, cursor=cur_study)
        if len(ratings) == 0:  # filter the ratings.
            continue
        r = [np.mean(ratings[pi_id]['ratings']) if pi_id in ratings else 0 for pi_id in pis_ids]
        for k, pi_id in enumerate(pis_ids):
            cl = 0
            if r[k] >= 4:
                cl = 1
            y_train[i * nb_pis + k] = cl  # int(np.ceil(r[k]))
            indexes.append((place_id, pi_id))

        # 2. Get the predictions from the models for the place (x).
        for j, clf in enumerate(clfs):
            predictions = clf._get_prediction(place_id)
            p = [predictions[pi_id]['score'] if pi_id in predictions else 0 for pi_id in pis_ids]
            for k in range(nb_pis):
                x_train[i * nb_pis + k, j] = p[k]
    print("[.] Done with x_train: %s, y_train: %s, indexes: %s (%.2f)" % (x_train.shape, y_train.shape, len(indexes), time.time()-stime))
    return x_train, y_train, indexes


def over_sample_training_set(X, y):
    # https://imbalanced-learn.readthedocs.io/en/stable/generated/imblearn.over_sampling.SMOTE.html
    print('[.] Re-sample training set...\n'
          '[.] Original dataset shape %s' % Counter(y))
    stime = time.time()
    sm = SMOTE()
    X_resampled, y_resampled = sm.fit_resample(X, y)
    print('[.] Re-sampled dataset shape %s (%.2f)' % (Counter(y_resampled), time.time()-stime))
    return X_resampled, y_resampled


def train_logistic_regression(X, y, persist=True):
    # Apply the logistic regression classifier.
    clf_lr = LogisticRegression(random_state=0, multi_class='multinomial', solver='newton-cg')

    # Train the logistic regression model.
    model = clf_lr.fit(X, y)
    if persist:
        joblib.dump(model, MODEL_EXPORT_NAME)

    return model


def get_model_cross_validation_performance(X, y):
    # Apply the logistic regression classifier.
    clf_lr = LogisticRegression(random_state=0, multi_class='multinomial', solver='newton-cg')

    # Get the confusion matrix
    # split the train and test sets
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)

    # Train model
    model = clf_lr.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print("Accuracy: %.2f%%" % (accuracy * 100.0))

    # Confusion matrix of the classes
    conf_mat = confusion_matrix(y_true=y_test, y_pred=y_pred)
    print('Confusion matrix:\n', conf_mat)

    # The mean score and the 95% confidence interval of the score estimate.
    stime = time.time()
    accuracy = cross_val_score(clf_lr, X, y, cv=5, scoring='accuracy')
    print("Accuracy: %0.2f (+/- %0.6f) (%2.f seconds)" % (accuracy .mean(), accuracy .std() * 2, time.time()-stime))

    stime = time.time()
    recall = cross_val_score(clf_lr, X, y, cv=5, scoring='recall')
    print("Recall: %0.2f (+/- %0.6f) (%2.f seconds)" % (recall.mean(), recall.std() * 2, time.time() - stime))

    stime = time.time()
    precision = cross_val_score(clf_lr, X, y, cv=5, scoring='precision')
    print("Precision: %0.2f (+/- %0.6f) (%2.f seconds)" % (precision.mean(), precision.std() * 2, time.time() - stime))

    stime = time.time()
    f1 = cross_val_score(clf_lr, X, y, cv=5, scoring='f1')
    print("F1: %0.2f (+/- %0.6f) (%2.f seconds)" % (f1.mean(), f1.std() * 2, time.time() - stime))


def get_performance_per_model():
    model_init()
    res = {}
    for place_id in place_ids:
        ratings = get_relevance_ratings(place_id, cursor=cur_study, connection=c_study)
        relevant_ratings = set([pi_id for pi_id in ratings.keys() if np.mean(ratings[pi_id]['ratings']) >= 4])
        tot_relevant_items = len(relevant_ratings)
        if tot_relevant_items == 0:
            continue

        for clf in clfs:
            idx = clf.idx()
            predictions = clf._get_prediction(place_id)
            y_pred = [(pi_id, predictions[pi_id]['score']) for pi_id in predictions.keys()]
            y_pred_sorted = sorted(y_pred, key=lambda i: i[1], reverse=True)
            if len(y_pred) == 0:
                continue

            for k in [1, 2, 3, 4, 5]:
                nb_relevant_items = sum(1 for i in range(k) if y_pred_sorted[i][0] in relevant_ratings)
                precision_at_k = nb_relevant_items / k
                recall_at_k = nb_relevant_items / tot_relevant_items
                if idx not in res:
                    res[idx] = {}
                if k not in res[idx]:
                    res[idx][k] = []
                res[idx][k].append((precision_at_k, recall_at_k))

            nb_relevant_items = sum(1 for i in range(len(y_pred_sorted)) if y_pred_sorted[i][0] in relevant_ratings)
            precision = nb_relevant_items / len(y_pred_sorted)
            recall = nb_relevant_items / tot_relevant_items
            if -1 not in res[idx]:
                res[idx][-1] = []
            res[idx][-1].append((precision, recall))

    for idx in res.keys():
        for k in res[idx].keys():
            if k != -1:
                print(idx, k, len(res[idx][k]), "P@%s" % k, np.mean([e[0] for e in res[idx][k]]), "R@%s" % k, np.mean([e[1] for e in res[idx][k]]))
            else:
                print(idx, k, len(res[idx][k]), "P", np.mean([e[0] for e in res[idx][k]]), "R", np.mean([e[1] for e in res[idx][k]]))


def get_performance_per_model_balanced_classes(debug=False):
    global pis_ids, nb_pis, clfs

    res = {}
    sm = SMOTE(k_neighbors=4)
    y_pred = np.zeros((len(pis_ids), 1), dtype=int)
    for place_id in place_ids:
        ratings = get_relevance_ratings(place_id, cursor=cur_study, connection=c_study)
        y_true = [1 if pi_id in ratings and np.mean(ratings[pi_id]['ratings']) >= 4 else 0 for pi_id in pis_ids]
        if sum(y_true) <= 5:
            # Safe-guard the minimum of samples required for the SMOTE algorithm
            continue

        for clf in clfs:
            idx = clf.idx()
            predictions = clf._get_prediction(place_id)
            y_pred[:,0] = [1 if pi_id in predictions and predictions[pi_id]['score'] >= 0.01 else 0 for pi_id in pis_ids]
            if sum(y_pred) == 0:
                continue

            if debug:
                print('[.] Original dataset shape %s' % Counter(y_true))
            y_pred_resampled, y_true_resampled = sm.fit_resample(y_pred, y_true)
            if debug:
                print('[.] Resampled dataset shape %s' % Counter(y_true_resampled))

            if idx not in res:
                res[idx] = []
            res[idx].append((
                accuracy_score(y_true_resampled, y_pred_resampled[:, 0]),
                precision_score(y_true_resampled, y_pred_resampled[:, 0]),
                recall_score(y_true_resampled, y_pred_resampled[:, 0]),
                f1_score(y_true_resampled, y_pred_resampled[:, 0])))

    avg = [0.0, 0.0, 0.0, 0.0]
    for idx in res.keys():
        avg[0] += np.mean([e[0] for e in res[idx]])
        avg[1] += np.mean([e[1] for e in res[idx]])
        avg[2] += np.mean([e[2] for e in res[idx]])
        avg[3] += np.mean([e[3] for e in res[idx]])

        print("%s\t%.3f\t%.3f\t%.3f\t%.3f" % ("\t".join(str(e) for e in idx),
              np.mean([e[0] for e in res[idx]]),    # Accuracy
              np.mean([e[1] for e in res[idx]]),    # Precision
              np.mean([e[2] for e in res[idx]]),    # Recall
              np.mean([e[3] for e in res[idx]]),))  # F1-score

    print("Mean performance: \n"
          "..A: %s \n..P: %s\n..R: %s\n..F1: %s" % (avg[0] / len(res), avg[1] / len(res), avg[2] / len(res), avg[3] / len(res)))


def get_performance_baseline_frequency_based(debug=False):
    global pis_ids, nb_pis

    # get the frequencies of the personal information
    pis_frequencies = {}
    count = 0
    for place_id in place_ids:
        ratings = get_relevance_ratings(place_id, cursor=cur_study, connection=c_study)
        for pi_id, r in ratings.items():
            if pi_id not in pis_frequencies:
                pis_frequencies[pi_id] = 0
            pis_frequencies[pi_id] += 1
            count += 1

    total_count = count + (nb_pis - len(pis_frequencies))
    pis_weights = [pis_frequencies[pi_id] / total_count if pi_id in pis_frequencies else 1.0/total_count for pi_id in pis_ids]
    print("min_weight:", total_count, (nb_pis - len(pis_frequencies), count))

    res = []
    sm = SMOTE(k_neighbors=4)
    y_pred = np.zeros((len(pis_ids), 1), dtype=int)
    for place_id in place_ids:
        ratings = get_relevance_ratings(place_id, cursor=cur_study, connection=c_study)
        y_true = [1 if pi_id in ratings and np.mean(ratings[pi_id]['ratings']) >= 4 else 0 for pi_id in pis_ids]
        if sum(y_true) <= 5:
            # Safe-guard the minimum of samples required for the SMOTE algorithm
            continue

        chosen_pis = set([choice(pis_ids, p=pis_weights) for _ in range(10)])
        y_pred[:,0] = [1 if pi_id in chosen_pis else 0 for pi_id in pis_ids]

        if debug:
            print('[.] Original dataset shape %s' % Counter(y_true))
        y_pred_resampled, y_true_resampled = sm.fit_resample(y_pred, y_true)
        if debug:
            print('[.] Resampled dataset shape %s' % Counter(y_true_resampled))

        res.append((accuracy_score(y_true_resampled, y_pred_resampled[:, 0]),
            precision_score(y_true_resampled, y_pred_resampled[:, 0]),
            recall_score(y_true_resampled, y_pred_resampled[:, 0]),
            f1_score(y_true_resampled, y_pred_resampled[:, 0])))

    print("A", np.mean([e[0] for e in res]),
          "P", np.mean([e[1] for e in res]),
          "R", np.mean([e[2] for e in res]),
          "F1", np.mean([e[3] for e in res]))


def predict_personal_information_for_place(place_id, mdl=None):
    if mdl is None:
        # load the model.
        mdl = joblib.load(MODEL_EXPORT_NAME)

    X_test_place = np.zeros((nb_pis, nb_clfs))

    for i, clf in enumerate(clfs):
        predictions = clf._get_prediction(place_id)
        p = [predictions[pi_id]['score'] if pi_id in predictions else 0 for pi_id in pis_ids]
        for j in range(nb_pis):
            X_test_place[j, i] = p[j]

    y_pred_place = mdl.predict(X_test_place)
    y_pred_place_proba = mdl.predict_proba(X_test_place)
    return [(pis_ids[i], y_pred_place[i], y_pred_place_proba[i]) for i in range(nb_pis)]


def predict_personal_information_for_all_places(mdl=None):
    if mdl is None:
        # load the model.
        mdl = joblib.load(MODEL_EXPORT_NAME)

    # 1. Get all the foursquare places.
    places = get_all_foursquare_places()
    rated_place_ids = set(place_ids)

    # 2. Predict the personal information for all the places.
    f_out = open(PLACES_PERSONAL_INFORMATION, 'w')
    csvwriter = csv.writer(f_out, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    count = 0
    for place_id in tqdm.tqdm(places, total=len(places)):
        if place_id in rated_place_ids:
            # get the average rating from the database.
            ratings = get_relevance_ratings(place_id, cursor=cur_study, connection=c_study)
            if len(ratings) != 0:  # filter the ratings.
                for pi_id, r in ratings.items():
                    avg_rating = np.mean(r['ratings'])
                    if avg_rating >= 2:
                        # normalize the average user rating
                        csvwriter.writerow([place_id, 'user', pi_id, pis[pi_id]['name'], avg_rating / 5.0])
                # go to the next step
                continue

        # predict the relevance rating using our model
        predictions = predict_personal_information_for_place(place_id, mdl)
        for pi_id, cls, proba in predictions:
            if cls == 1:
                csvwriter.writerow([place_id, 'predict', pi_id, pis[pi_id]['name'], proba[1]])
    f_out.close()
    print("[.] Done with %s venues" % count)


def model_init():
    global c_study, cur_study, pis, pis_ids, nb_pis, place_ids, nb_places, clfs, nb_clfs

    # 0-0. Init.
    stime = time.time()
    c_study, cur_study = utils.connect_to_db("study", cursor_type=psycopg2.extras.DictCursor)
    print("[.] Init - %.2f" % (time.time() - stime))

    # 0-1. Get the personal information.
    start_time = time.time()
    pis = foursquare.load_personal_information()
    pis_ids = [pi['pi_id'] for pi in pis.values()]
    nb_pis = len(pis_ids)
    print("[.] Got %s personal information ids (%.2f)" % (nb_pis, time.time() - start_time))

    # 0-2. Get the classifiers
    start_time = time.time()
    params = get_all_classifiers()
    clfs = []
    for param in params:
        clfs.append(Classifier(param, pis_ids))
    nb_clfs = len(clfs)
    print("[.] Got %s classifiers (%.2f)" % (nb_clfs, time.time() - start_time))

    # 0-3. Get the places
    start_time = time.time()
    place_ids = get_all_distinct_place_ids(connection=c_study, cursor=cur_study)
    nb_places = len(place_ids)
    print("[.] Got %s place ids (%.2f)" % (nb_places, time.time() - start_time))


def print_usage():
    print('usage: \n'
          '  {name} train\n'
          '  {name} stats\n'
          '  {name} predict venue_id\n'
          '  {name} predict-all'.format(name=sys.argv[0]))


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print_usage()
        sys.exit(0)

    argument = sys.argv[1]
    if argument == 'train':
        model_init()

        # 1. Get the training set
        X, y, idx = create_training_set_blending()

        # 2. Balance the classes with over-sampling
        X, y = over_sample_training_set(X=X, y=y)

        # 4. Train the logistic regression meta-classifier
        model = train_logistic_regression(X=X, y=y, persist=True)

        # 5. Print the coefficients assigned by the model.
        for i in range(len(clfs)):
            print(i, clfs[i].idx(), model.coef_[0,i], "\t%.3f" % model.coef_[0,i])

    elif argument == 'stats':
        model_init()

        # 1. Get the training set
        X, y, idx = create_training_set_blending()

        # 2. Balance the classes with over-sampling
        X, y = over_sample_training_set(X=X, y=y)

        # 2. Get the model performance
        get_model_cross_validation_performance(X=X, y=y)

        # TODO: get the confusion matrix averaged over 10 trials
    elif argument == 'stats-each':
        model_init()

        # print('Performance at k')
        # get_performance_per_model()
        print('Balanced classes')
        get_performance_per_model_balanced_classes(debug=False)
        print('Baseline (frequency-based)')
        get_performance_baseline_frequency_based(debug=False)

    elif argument == 'predict':
        if len(sys.argv) != 3:
            print("Error: Enter a venue identifier")
            print_usage()
            sys.exit(0)

        model_init()
        place_id = sys.argv[2]
        ratings = get_relevance_ratings(place_id)
        r = [np.mean(ratings[pi_id]['ratings']) if pi_id in ratings else 0 for pi_id in pis_ids]

        pred = predict_personal_information_for_place(place_id)

        for i in range(nb_pis):
            if pred[i][1] == 1:
                print("%s: %s %s (%s)" % (pis[pis_ids[i]]['name'], pred[i][1], pred[i][2], r[i]))

    elif argument == 'predict-all':
        print("[.] predict all places")

        model_init()
        predict_personal_information_for_all_places()

