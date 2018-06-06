import csv
from collections import OrderedDict


def process_google_adwords_interests():
    count = 0
    parent_ids = set()
    interests = OrderedDict()
    with open('google_adwords_interests.csv', 'r') as csvfile:
        csvfile.readline()
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            parent_ids.add(row[2])
            interests[row[1]] = (row[0], row[2])

    print(len(parent_ids), len(interests))

    with open('google_adwords_interests_fileted.csv', 'w') as csvfile:
        writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        for interest_id, (name, parent_id) in interests.items():
            if interest_id in parent_ids:
                continue

            writer.writerow([interest_id, name, parent_id, interests[parent_id][0]])


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


def get_google_adwords_tree():
    interests = OrderedDict()
    with open('google_adwords_interests.csv', 'r') as csvfile:
        csvfile.readline()
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            interests[row[1]] = (row[0], row[2])

    parents = {"0": []}
    nodes = {"0": Node("0", "root")}
    for k, v in interests.items():
        parent_id = v[1]
        if parent_id not in parents:
            parents[parent_id] = []
        parents[parent_id].append(k)
        nodes[k] = Node(k, v[0])

    print("number of parents: {}".format(len(parents)))
    print("number of nodes: {}".format(len(nodes)))

    for parent in parents.keys():
        node = nodes[parent]
        for child in parents[parent]:
            node.add_child(nodes[child])

    print(nodes["0"])


if __name__ == '__main__':
    get_google_adwords_tree()
