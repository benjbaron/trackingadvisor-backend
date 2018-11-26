from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import csv
import tqdm
import mmap
import math
import collections
import random
import numpy as np
import calendar
import datetime
import tensorflow as tf
import pprint
import pickle
from six.moves import xrange


# Define paths to the Foursquare (FSQ) datasets
FQS_CHECKINS_PATH = "/home/ucfabb0/enigma/data/foursquare/dataset_TIST2015/"
FQS_CHECKINS_FILTERED_POIS = FQS_CHECKINS_PATH + "dataset_TIST2015_POIs_filtered_redirected.txt"
FQS_CHECKINS_FILTERED = FQS_CHECKINS_PATH + "dataset_TIST2015_Checkins_filtered_redirected.txt"
PLACES_PERSONAL_INFORMATION = 'foursquare_places_personal_information.txt'


# Helper functions.
def date_to_timestamp(s):
    """ Convert "str" to millisecond timestamp. """
    d = s[:-10]+s[-4:]
    return 1000*int(calendar.timegm(datetime.datetime.strptime(d, "%a %b %d %H:%M:%S %Y").utctimetuple()))


def get_num_lines(file_path):
    """ :returns number of lines in the file "file_path". """
    fp = open(file_path, "r+")
    buf = mmap.mmap(fp.fileno(), 0)
    lines = 0
    while buf.readline():
        lines += 1
    return lines


def get_place_info():
    """" :returns Dictionary where each place identifier is associated to the information of the place. """

    place_info = {}
    with open(FQS_CHECKINS_FILTERED_POIS, 'r') as f:
        count = 0
        for line in tqdm.tqdm(f, total=get_num_lines(FQS_CHECKINS_FILTERED_POIS)):
            fields = line.strip().split('\t')

            venue_id = fields[0]
            try:
                lat = float(fields[1])
                lon = float(fields[2])
                category = fields[3]
                cc = fields[4]
                name = fields[5]
                emoji = fields[6]

                if venue_id not in place_info:
                    place_info[venue_id] = {
                        'name': name,
                        'cc': cc,
                        'category': category,
                        'emoji': emoji
                    }
                    count += 1
            except:
                print(venue_id)

    print("[.] Processed %s places" % count)
    print("[.] Got %s places from the Foursquare places dataset." % (len(place_info)))
    return place_info


def get_checkins_at_places():
    """ :returns Dictionary where each place is associated to a list of checkins (user_id, timestamps). """

    checkins_at_places = {}
    with open(FQS_CHECKINS_FILTERED, 'r') as f:
        count = 0
        for line in tqdm.tqdm(f, total=get_num_lines(FQS_CHECKINS_FILTERED)):
            fields = line.strip().split('\t')
            user_id = fields[0]
            venue_id = fields[1]
            date_string = fields[2]
            utc_offset = int(fields[3])
            try:
                d = date_to_timestamp(date_string)
                d += utc_offset
            except ValueError as e:
                print("error with line: %s" % line.rstrip())
                continue

            if venue_id not in checkins_at_places:
                checkins_at_places[venue_id] = []
            checkins_at_places[venue_id].append((user_id, d))

    print("[.] Processed %s checkins" % count)
    print("[.] Got %s checkins at places from the Foursquare checkins dataset." % (len(checkins_at_places)))
    return checkins_at_places


def get_user_checkins_at_places(sort=True):
    """ :returns Dictionary where each user is associated to a list of checkins (venue_id, timestamps). """

    user_checkins_at_places = {}
    with open(FQS_CHECKINS_FILTERED, 'r') as f:
        count = 0
        for line in tqdm.tqdm(f, total=get_num_lines(FQS_CHECKINS_FILTERED)):
            fields = line.strip().split('\t')
            user_id = fields[0]
            venue_id = fields[1]
            date_string = fields[2]
            utc_offset = int(fields[3])
            try:
                d = date_to_timestamp(date_string)
                d += utc_offset
            except ValueError as e:
                print("error with line: %s" % line.rstrip())
                continue

            if user_id not in user_checkins_at_places:
                user_checkins_at_places[user_id] = []
            user_checkins_at_places[user_id].append((venue_id, d))
            count += 1

    print("[.] Processed %s checkins" % count)
    print("[.] Got %s users who checked-in from the Foursquare checkins dataset." % (len(user_checkins_at_places)))

    if sort:
        # Sort the user checkins by date
        user_checkins_at_places_sorted = {}
        for user_id, checkins in user_checkins_at_places.items():
            user_checkins_at_places_sorted[user_id] = [e[0] for e in sorted(checkins, key=lambda x: x[1], reverse=False)]
        return user_checkins_at_places_sorted

    return user_checkins_at_places


def get_personal_information_from_places(sort=True):
    """ :returns Two dictionaries as follows:
            - Dictionary where each place is associated to a list of personal information
              either predicted or given by the users (pi_id, type, score).
            - Dictionary where each personal information identifier is associated to their name.
    """

    personal_information_at_places = {}
    personal_information_names = {}
    with open(PLACES_PERSONAL_INFORMATION, 'r') as f:
        csvreader = csv.reader(f, delimiter=',', quotechar='"')
        count = 0
        for row in tqdm.tqdm(csvreader, total=get_num_lines(PLACES_PERSONAL_INFORMATION)):
            place_id = row[0]
            prediction_type = row[1]
            pi_id = row[2]
            name = row[3]
            score = row[4]

            if pi_id not in personal_information_names:
                personal_information_names[pi_id] = name

            if place_id not in personal_information_at_places:
                personal_information_at_places[place_id] = []
            personal_information_at_places[place_id].append((pi_id, prediction_type, score))
            count += 1

    print("[.] Processed %s personal information." % count)
    print("[.] Got %s places with personal information and %s personal information." % (len(personal_information_at_places), len(personal_information_names)))

    if sort:
        personal_information_at_places_sorted = {}
        for place_id, pis in personal_information_at_places.items():
            personal_information_at_places_sorted[place_id] = [e[0] for e in sorted(pis, key=lambda x: x[2], reverse=True)]
        return personal_information_at_places_sorted, personal_information_names

    return personal_information_at_places, personal_information_names


def generate_batch(batch_size, num_skips, skip_window, context_size):
    """
    :param batch_size: Size of the batch
    :param num_skips: Number of times to reuse an input to generate a label
    :param skip_window: Number of words (i.e., personal information) to consider left and right
    :param context_size: Number of personal information to consider per place
    :return: Returns a batch and labels of respective shapes:
     - Batch: (batch_size, context_size)
     - Labels: (batch_size, label)
    """

    global data_index, user_id_index

    # Enforce the assumptions.
    assert batch_size % (num_skips * context_size) == 0
    assert num_skips <= 2 * skip_window

    # get the user id we will use for this iteration
    user_id = user_ids[user_id_index][0]

    batch = np.ndarray(shape=(batch_size, context_size), dtype=np.int32)
    labels = np.ndarray(shape=(batch_size, 1), dtype=np.int32)

    span = 2 * skip_window + 1               # [ skip_window skip_window place_target skip_window skip_window ]
    buffer = collections.deque(maxlen=span)  # create a queue

    if data_index + span > len(data_places[user_id]):
        data_index = 0  # reset

    buffer.extend(data_places[user_id][data_index:data_index + span])
    data_index += span

    for i in range(batch_size // (num_skips * context_size)):
        # i the number of iterations corresponds to the number of places we consider with their context
        # the context corresponds to the places left and right of the place target (span) and their personal information

        # choose num_skips random places in the context of the target
        context_words = [w for w in range(span) if w != skip_window]
        words_to_use = random.sample(context_words, num_skips)

        # print(" ", i, "target:", buffer[skip_window], "buffer:", buffer, context_words, words_to_use)

        for j, context_word in enumerate(words_to_use):
            # print("   ", j, "context:", buffer[context_word], "label:", buffer[skip_window], "context pi:",
            #       places[reverse_dictionary_places[buffer[context_word]]][0])

            p_info = place_info[reverse_dictionary_places[buffer[context_word]]]
            # print(p_info['emoji'], " ", p_info['name'])
            p = places[reverse_dictionary_places[buffer[context_word]]]
            # print([pi_names[pi] for pi in p])

            # target place and personal information within the context of the target place
            pis_batch = places[reverse_dictionary_places[buffer[skip_window]]]
            pis_batch_list = [dictionary_pi[pis_batch[ctx % len(pis_batch)]] for ctx in range(context_size)]
            for k in range(context_size):
                idx = (i * num_skips + j) * context_size + k

                # the batch list remains the same for all the personal information within the context.
                batch[idx, :] = pis_batch_list

                # kth personal information of the place within the context of the target place.
                pis_label = dictionary_pi[p[k % len(p)]] if len(p) < k else 0
                labels[idx, :] = pis_label

        if data_index == len(data_places[user_id]):
            if user_id_index+1 != len(user_ids):
                # go to the next user index.
                user_id_index += 1
                user_id = user_ids[user_id_index][0]

            buffer.extend(data_places[user_id][0:span])
            data_index = span
        else:
            # print(".. data_places", user_id, "len", len(data_places[user_id]), data_index)
            buffer.append(data_places[user_id][data_index])
            data_index += 1

    # Backtrack a little bit to avoid skipping words in the end of a batch
    data_index = (data_index + len(data_places[user_id]) - span) % len(data_places[user_id])

    return batch, labels


embedding_size = 300     # Dimension of the embedding vector
vocabulary_size = 500    # Initial size of the vocabulary
batch_size = 400         # Size of the batch
skip_window = 2          # How many words (i.e., personal information) to consider left and right
num_skips = 4            # How many times to reuse an input to generate a label
context_size = 5         # context == number of personal information to consider per place


data_index = 0
user_id_index = 0


if __name__ == '__main__':
    place_info = get_place_info()
    places, pi_names = get_personal_information_from_places(sort=True)
    user_checkins_at_places = get_user_checkins_at_places(sort=True)

    all_checkins = [venue_id for c in user_checkins_at_places.values() for venue_id in c]
    all_personal_information = [pi_id for pis in places.values() for pi_id in pis]

    count_places = collections.Counter(all_checkins).most_common()

    dictionary_places = dict()
    for place, _ in count_places:
        dictionary_places[place] = len(dictionary_places)
    reverse_dictionary_places = dict(zip(dictionary_places.values(), dictionary_places.keys()))
    print("dictionary_places", len(dictionary_places))
    print("reverse_dictionary_places", len(reverse_dictionary_places))

    dictionary_pi = dict()
    count_pi = [['UNK', -1]]
    pi_names['UNK'] = 'unknown'

    count_pi.extend(collections.Counter(all_personal_information).most_common())
    for pi, _ in count_pi:
        dictionary_pi[pi] = len(dictionary_pi)
    reverse_dictionary_pi = dict(zip(dictionary_pi.values(), dictionary_pi.keys()))
    print("dictionary_pi", len(dictionary_pi))
    print("reverse_dictionary_pi", len(reverse_dictionary_pi))

    # set the vocabulary size to the total number of personal information
    vocabulary_size = len(dictionary_pi)

    data_places = dict()  # per-user places
    user_ids = list()     # list of user identifiers
    for user_id, checkin_sequence in user_checkins_at_places.items():
        if len(checkin_sequence) < 5:
            continue

        data_places[user_id] = list()
        for place in checkin_sequence:
            if place in dictionary_places and place in places:
                index = dictionary_places[place]
                data_places[user_id].append(index)
        if len(data_places[user_id]) < 5:
            del data_places[user_id]
        else:
            user_ids.append((user_id, len(data_places[user_id])))

    batch, labels = generate_batch(batch_size=8, num_skips=2, skip_window=1, context_size=4)
    for i in range(8):
        print(batch[i], [pi_names[reverse_dictionary_pi[e]] for e in batch[i]], '->', labels[i, 0], pi_names[reverse_dictionary_pi[labels[i, 0]]])

    # Step 4: Build and train a bagged skip-gram model.
    valid_size = 16  # Random set of words to evaluate similarity on.
    valid_window = 100  # Only pick dev samples in the head of the distribution.
    valid_examples = np.random.choice(valid_window, valid_size, replace=False)
    num_sampled = 64  # Number of negative examples to sample.

    graph = tf.Graph()

    with graph.as_default():
        print('starting...')

        # Input data.
        train_inputs = tf.placeholder(tf.int32, shape=[batch_size, context_size])
        train_labels = tf.placeholder(tf.int32, shape=[batch_size, 1])
        valid_dataset = tf.constant(valid_examples, dtype=tf.int32)

        # Ops and variables pinned to the CPU because of missing GPU implementation
        with tf.device('/cpu:0'):
            print('start with cpu:0...')

            # Look up embeddings for inputs.
            embeddings = tf.Variable(tf.random_uniform([vocabulary_size, embedding_size], -1.0, 1.0))
            embed = tf.nn.embedding_lookup(embeddings, train_inputs)
            # take mean of embeddings of context words for context embedding
            embed_context = tf.reduce_mean(embed, 1)

            # Construct the variables for the NCE loss
            nce_weights = tf.Variable(
                tf.truncated_normal([vocabulary_size, embedding_size],
                                    stddev=1.0 / math.sqrt(embedding_size)))
            nce_biases = tf.Variable(tf.zeros([vocabulary_size]))

        print('declare NCE loss function')
        # Compute the average NCE loss for the batch.
        # tf.nce_loss automatically draws a new sample of the negative labels each
        # time we evaluate the loss.
        loss = tf.reduce_mean(
            tf.nn.nce_loss(weights=nce_weights,
                           biases=nce_biases,
                           labels=train_labels,
                           inputs=embed_context,
                           num_sampled=num_sampled,
                           num_classes=vocabulary_size))

        print('construct SCG optimizer')
        # Construct the SGD optimizer using a learning rate of 1.0.
        optimizer = tf.train.GradientDescentOptimizer(1.0).minimize(loss)

        print('construct cosine similarity')
        # Compute the cosine similarity between minibatch examples and all embeddings.
        norm = tf.sqrt(tf.reduce_sum(tf.square(embeddings), 1, keepdims=True))
        normalized_embeddings = embeddings / norm
        valid_embeddings = tf.nn.embedding_lookup(normalized_embeddings, valid_dataset)
        similarity = tf.matmul(valid_embeddings, normalized_embeddings, transpose_b=True)

        print('init all variables')
        # Add variable initializer.
        init = tf.global_variables_initializer()

        # Add ops to save and restore all the variables.
        saver = tf.train.Saver({"embeddings": embeddings})

    # Step 5: Begin training.
    num_steps = 100001

    with tf.Session(graph=graph) as session:
        # We must initialize all variables before we use them.
        init.run()
        print("Initialized")

        average_loss = 0
        for step in xrange(num_steps):
            batch_inputs, batch_labels = generate_batch(batch_size, num_skips, skip_window, context_size)
            feed_dict = {train_inputs: batch_inputs, train_labels: batch_labels}

            # We perform one update step by evaluating the optimizer op (including it
            # in the list of returned values for session.run()
            _, loss_val = session.run([optimizer, loss], feed_dict=feed_dict)
            average_loss += loss_val

            if step % 2000 == 0:
                if step > 0:
                    average_loss /= 2000
                # The average loss is an estimate of the loss over the last 2000 batches.
                print("Average loss at step ", step, ": ", average_loss)
                average_loss = 0

            # Note that this is expensive (~20% slowdown if computed every 500 steps)
            if step % 10000 == 0:
                sim = similarity.eval()
                for i in xrange(valid_size):
                    valid_word = pi_names[reverse_dictionary_pi[valid_examples[i]]]
                    top_k = 10  # number of nearest neighbors
                    nearest = (-sim[i, :]).argsort()[1:top_k + 1]
                    log_str = "Nearest to %s:" % valid_word
                    for k in xrange(top_k):
                        close_word = pi_names[reverse_dictionary_pi[nearest[k]]]
                        log_str = "%s %s," % (log_str, close_word)
                    print(log_str)
        final_embeddings = normalized_embeddings.eval()

        # Save the model
        # Save vocabulary dictionary
        with open('personal_information_vocab.pkl', 'wb') as f:
            pickle.dump(word_dictionary, f)

        # Save embeddings
        model_checkpoint_path = 'bagged_skip_gram_personal_information_embeddings.ckpt'
        save_path = saver.save(sess, model_checkpoint_path)
        print('Model saved in file: {}'.format(save_path))


    # Step 6: Visualize the embeddings.
    def plot_with_labels(low_dim_embs, labels, filename='tsne.png'):
        assert low_dim_embs.shape[0] >= len(labels), "More labels than embeddings"
        plt.figure(figsize=(18, 18))  # in inches
        for i, label in enumerate(labels):
            x, y = low_dim_embs[i, :]
            plt.scatter(x, y)
            plt.annotate(label,
                         xy=(x, y),
                         xytext=(5, 2),
                         textcoords='offset points',
                         ha='right',
                         va='bottom')

        plt.savefig(filename)

    try:
        from sklearn.manifold import TSNE
        import matplotlib.pyplot as plt

        tsne = TSNE(perplexity=30, n_components=2, init='pca', n_iter=5000)
        plot_only = 500
        low_dim_embs = tsne.fit_transform(final_embeddings[:plot_only, :])
        labels = [pi_names[reverse_dictionary_pi[i]] for i in xrange(plot_only)]
        plot_with_labels(low_dim_embs, labels)

    except ImportError:
        print("Please install sklearn, matplotlib, and scipy to visualize embeddings.")









