from flask import Flask, render_template, request, session, send_file, url_for, redirect
from flask_basicauth import BasicAuth

import os
import re
import json
import requests
import random
import pika
import uuid
import psycopg2

import foursquare
import keys
import utils
import personal_information
import user_traces_db
import study

RABBITMQ_HOST = 'colossus07'
RABBITMQ_QUEUE = 'rpc_study_queue'


# http://flask.pocoo.org/snippets/35/
class ReverseProxied(object):
    """ Wrap the application in this middleware and configure the
    front-end server to add these headers, to let you quietly bind
    this to a URL other than / and to an HTTP scheme that is
    different than what is used locally.

    In nginx:
    location /myprefix {
        proxy_pass http://192.168.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Script-Name /myprefix;
        }

    :param app: the WSGI application """

    def __init__(self, app, script_name=None, scheme=None, server=None):
        self.app = app
        self.script_name = script_name
        self.scheme = scheme
        self.server = server

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '') or self.script_name
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        scheme = environ.get('HTTP_X_SCHEME', '') or self.scheme
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        server = environ.get('HTTP_X_FORWARDED_SERVER', '') or self.server
        if server:
            environ['HTTP_HOST'] = server
        return self.app(environ, start_response)


# https://www.rabbitmq.com/tutorials/tutorial-six-python.html
class WorkerRpcClient(object):
    def __init__(self):
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))

        self.channel = self.connection.channel()

        result = self.channel.queue_declare(exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(self.on_response, no_ack=True,
                                   queue=self.callback_queue)

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = body

    def call(self, s):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(exchange='',
                                   routing_key=RABBITMQ_QUEUE,
                                   properties=pika.BasicProperties(
                                       reply_to=self.callback_queue,
                                       correlation_id=self.corr_id),
                                   body=str(s))
        while self.response is None:
            self.connection.process_data_events()

        return json.loads(self.response)


app = Flask(__name__)
app.config['SECRET_KEY'] = 'seManTiCa'

app.config['SECRET_KEY'] = 'SeMaNtiCa'
app.config['BASIC_AUTH_USERNAME'] = 'semantica'
app.config['BASIC_AUTH_PASSWORD'] = 'semantica-isslab'

app.wsgi_app = ReverseProxied(app.wsgi_app, script_name='/semantica')
basic_auth = BasicAuth(app)


def get_ip_address(request):
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    print("IP address = %s" % ip_address)
    if ',' in ip_address:
        ip_address = ip_address.split(',')[0].strip()

    return ip_address



@app.route('/')
@basic_auth.required
def show_study_stats():
    stats = study.get_stats()
    return render_template('stats/stats.html', stats=stats)


@app.route('/update')
@basic_auth.required
def study_stats_update():
    study.update_place_records()
    return json.dumps({"success": "ok"})


@app.route('/users')
@basic_auth.required
def show_stats_users():
    stats = study.get_stats()
    return render_template('stats/users.html', page='users', stats=stats)


@app.route('/pi')
@basic_auth.required
def show_stats_pi():
    return render_template('stats/pi.html', page='pi')


@app.route('/models')
@basic_auth.required
def show_stats_models():
    models = study.get_model_stats()
    return render_template('stats/models.html', page='models', models=models)


@app.route('/place')
@basic_auth.required
def show_stats_place():
    return render_template('stats/placeSearch.html', page='place')


@app.route('/places')
@basic_auth.required
def show_stats_places():
    places = study.get_all_distinct_selected_places()
    return render_template('stats/places.html', page='places', places=places)


@app.route('/placepi')
@basic_auth.required
def show_place_pi():
    place_id = request.args.get('place_id')
    place = foursquare.get_place(place_id)
    return render_template('stats/placePi.html', place=place)


@app.route('/searchplace')
def search_place():
    query = request.args.get('query')
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    ne_lat = request.args.get('nelat', '')
    ne_lon = request.args.get('nelon', '')
    sw_lat = request.args.get('swlat', '')
    sw_lon = request.args.get('swlon', '')

    location = {"lon": lon, "lat": lat}
    bounds = {"ne": {"lat": ne_lat, "lon": ne_lon}, "sw": {"lat": sw_lat, "lon": sw_lon}}

    return json.dumps(study.get_places(query, location, bounds))


@app.route('/location')
def get_location():
    ip_address = get_ip_address(request)

    key = random.choice(keys.IPSTACK_KEYS)
    send_url = 'http://api.ipstack.com/%s?access_key=%s' % (ip_address, key)
    r = requests.get(send_url).json()

    return json.dumps({'lat': r['latitude'], 'lon': r['longitude']})


@app.route('/geocode')
def search_geocode():
    query = request.args.get('query')
    return json.dumps(study.geocode_autocomplete(query))


@app.route('/getplacedetails')
def get_place_details():
    place_id = request.args.get('id')
    return json.dumps(foursquare.get_place(place_id))


@app.route('/computeplacepi')
def compute_place_personal_information():
    place_id = request.args.get('id')
    print("Computing personal information for place %s" % place_id)

    print(" [x] Instantiating a RPC client")
    worker_rpc = WorkerRpcClient()
    print(" [x] Requesting interests for place (%s)" % place_id)
    response = worker_rpc.call(place_id)
    print(" [x] Got %s interests" % len(response))

    return json.dumps(response)


@app.route('/getplaceratings')
@basic_auth.required
def get_place_ratings():
    place_id = request.args.get('id')
    print(place_id, request.args)
    ratings = study.get_relevance_ratings(place_id)
    print(ratings)
    return json.dumps(ratings)


def compute_place_interests(room, places):
    print(" [x] Instantiating a RPC client")
    worker_rpc = WorkerRpcClient()

    socketio.emit('update', {'progress': 0, 'message': "Processing"}, namespace='/load', room=room)
    socketio.sleep(0.05)

    i = 1
    nb_places = len(places)
    for place_id, place in places.items():
        study.save_place(room, place)
        print(" [x] Requesting interests for place \"%s\" (%s)" % (place['name'], place_id))
        response = worker_rpc.call(place_id)
        print(" [x] Got %s interests" % len(response))

        progress = float(i) / nb_places
        socketio.emit('update', {'progress': progress, 'message': "%s" % place['name']}, namespace='/load', room=room)
        socketio.sleep(0.05)
        i += 1


if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)
