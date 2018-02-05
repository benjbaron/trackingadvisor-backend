import sys
import utils

from collections import Counter
from nltk.stem import WordNetLemmatizer
from multiprocessing.dummy import Pool as ThreadPool, Manager as ThreadManager
import string

import nltk
from nltk.corpus import wordnet as wn
from nltk.stem.porter import PorterStemmer
from nltk.corpus import stopwords
from nltk import wordpunct_tokenize
from nltk.util import ngrams
from nltk.stem.wordnet import WordNetLemmatizer
nltk.download('wordnet')

from nltk.parse.corenlp import CoreNLPDependencyParser


uri_label = "<http://www.w3.org/2000/01/rdf-schema#label>"
uri_parent = "<http://www.w3.org/2000/01/rdf-schema#subClassOf>"
uri_thing = "<http://www.w3.org/2002/07/owl#Thing>"
uri_subject = "<http://purl.org/dc/terms/subject>"
uri_type = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"


lmtzr = WordNetLemmatizer()
dep_parser = CoreNLPDependencyParser(url='http://localhost:9000')


def get_name(uri):
    pattern = r".*\b\/(?:\w+\:)?([^\/:]+)\>$"
    m = re.match(pattern, uri)
    try:
        name = m.group(1).replace("_", " ")
    except AttributeError as e:
        print("Problem with uri {}".format(uri))
        return ""
    return name


def get_tokens(text):
    lowers = text.lower()
    no_punctuation = lowers.translate(lowers.maketrans('', '', string.punctuation))
    tokens = nltk.word_tokenize(no_punctuation)
    return tokens


def stem_tokens(tokens, stemmer):
    stemmed = []
    for item in tokens:
        stemmed.append(stemmer.stem(item))
    return stemmed


def lemmatize_tokens(tokens, lmtzr):
    lemmatized = []
    for item in tokens:
        lemmatized.append(lmtzr.lemmatize(item))
    return lemmatized


def remove_stopwords(tokens, language="english"):
    return [w for w in tokens if not w in stopwords.words(language)]


def get_ngrams(tokens):
    res = []
    res += [tuple([t]) for t in tokens]
    res += list(ngrams(tokens, 2))
    res += list(ngrams(tokens, 3))
    res += list(ngrams(tokens, 4))
    res += list(ngrams(tokens, 5))
    return res


def get_en_label(uri):
    if uri_label in ontology[uri]:
        labels = ontology[uri][uri_label]
        for label in labels:
            if "@en" in label:
                return label
        return labels[0]
    return ""


def get_parent(uri):
    if uri_parent in ontology[uri]:
        for p in ontology[uri][uri_parent]:
            if 'dbpedia' in p or p == uri_thing:
                return p
    return ""


def build_ontology_tree(ontology):
    class Node(object):
        def __init__(self, uri, label):
            self.uri = uri
            self.label = label
            self.children = []
            self.parent = None

        def add_child(self, obj):
            self.children.append(obj)
            obj.parent = self

        def is_leaf(self):
            return len(self.children) == 0

        def __str__(self):
            stack = [(self, 0)]
            path = []
            s = ""
            while stack:
                node, level = stack.pop()
                if node in path:
                    continue

                if level == 0:
                    s += "   " + str(node.label)
                else:
                    s += "\n" + " " * (level * 3) + "|- " + str(node.label) + " (%s)" % node.is_leaf()
                path.append(node)

                for child in node.children:
                    stack.append((child, level + 1))
            return s

    parents = {uri_thing: []}
    nodes = {uri_thing: Node(uri_thing, 'thing')}
    for k, v in list(ontology.items()):
        parent_uri = get_parent(k)
        if parent_uri == '':
            continue
        if parent_uri not in parents:
            parents[parent_uri] = []
        parents[parent_uri].append(k)
        nodes[k] = Node(k, get_name(k))

    print("number of parents: {}".format(len(parents)))
    print("number of nodes: {}".format(len(nodes)))

    for parent in parents.keys():
        node = nodes[parent]
        for child in parents[parent]:
            node.add_child(nodes[child])

    return nodes


def get_geo_mapped_types(instances, nodes, geo_mapped_instances):
    def get_ontology_leaf_types(nodes):
        leaf_types = set()
        for uri, node in nodes.items():
            if node.is_leaf():
                leaf_types.add(uri)

        return leaf_types

    leaf_types = get_ontology_leaf_types(nodes)
    print("We have {} leaf types".format(len(leaf_types)))

    # 1 - get all the subjects of the geo-mapped  instances
    geo_mapped_subjects = []
    geo_mapped_types_subjects = {}
    geo_mapped_types_instances = {}
    for k, v in list(geo_mapped_instances.items()):
        if k in instances:
            if uri_type in instances[k]:
                intersection = set(instances[k][uri_type]) & leaf_types
                if intersection:
                    for e in intersection:
                        if e not in geo_mapped_types_instances:
                            geo_mapped_types_instances[e] = set()
                        geo_mapped_types_instances[e].add(k)
                    if uri_subject in instances[k]:
                        geo_mapped_subjects += instances[k][uri_subject]
                        for e in intersection:
                            if e not in geo_mapped_types_subjects:
                                geo_mapped_types_subjects[e] = set()
                            geo_mapped_types_subjects[e] |= set(instances[k][uri_subject])

    geo_mapped_subjects_counter = Counter(geo_mapped_subjects)

    print("Done with %d unique subjects" % (len(geo_mapped_subjects_counter)))
    print("Done with %d unique type subjects" % (len(geo_mapped_types_subjects)))
    print("Done with %d unique type instances" % (len(geo_mapped_types_instances)))

    return geo_mapped_subjects_counter, geo_mapped_types_instances, geo_mapped_types_subjects


def get_instance_roots(instances, output_file):
    # 2 - get the roots of the categories
    def get_uri_root(uri):
        name = get_name(uri).lower()
        if name == "":
            return uri, ""

        graph, = dep_parser.raw_parse(name)
        root = graph.root['word']
        return uri, lmtzr.lemmatize(root)

    pool = ThreadPool(20)
    result = pool.map_async(get_uri_root, instances)
    result.wait()
    roots = result.get()

    with open(output_file, 'w') as f:
        for uri, root in roots:
            f.write("%s\t%s\n" % (uri, root))

    print("Done with {} roots".format(len(roots)))
    return roots


def get_instance_ngrams(instances):
    def get_uri_ngrams(uri):
        name = get_name(uri).lower()
        tokens = get_tokens(name)
        lemmatized = lemmatize_tokens(tokens, lmtzr)
        return get_ngrams(lemmatized)

    pool = ThreadPool(20)
    result = pool.map_async(get_uri_ngrams, instances)
    result.wait()
    ngrams = [item for sublist in result.get() for item in sublist]

    return ngrams
