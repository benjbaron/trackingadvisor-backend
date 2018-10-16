import eventlet
eventlet.monkey_patch()

from functools import wraps
from flask import Flask, render_template, request, session, send_file, url_for, redirect
from flask_basicauth import BasicAuth
from flask_socketio import SocketIO, emit, send, join_room
from flask import _request_ctx_stack as stack

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
MOBILE_DEVICES = 'iPhone|iPod|Android.*Mobile|Windows.*Phone|dream|blackberry|CUPCAKE|webOS|incognito|webmate'
MOBILE_DEVICES_PATTERN = re.compile(MOBILE_DEVICES.lower())


def mobile_template(template=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ctx = stack.top
            if ctx is not None and hasattr(ctx, 'request'):
                request = ctx.request

                user_agent = request.user_agent.string.lower()
                match = MOBILE_DEVICES_PATTERN.search(user_agent)
                is_mobile = match is not None
                kwargs['template'] = re.sub(r'{(.+?)}',
                                            r'\1' if is_mobile else '',
                                            template)
                if is_mobile:
                    print("Mobile device")
                else:
                    print("Not mobile device")

                return f(*args, **kwargs)
        return wrapper
    return decorator


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

socketio = SocketIO(app, message_queue="amqp://colossus07/socketio")


def get_ip_address(request):
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    print("IP address = %s" % ip_address)
    if ',' in ip_address:
        ip_address = ip_address.split(',')[0].strip()

    return ip_address


def start_session():
    # create a new session
    if 'sid' not in session:
        session_id = "SemanticaStudy-" + utils.id_generator()
        print("created session-id: %s" % session_id)
        session['sid'] = session_id
    else:
        session_id = session['sid']
        print("using session-id: %s" % session_id)

    study.start_session(session_id, get_ip_address(request))


@app.route('/')
@mobile_template('{mobile/}welcome.html')
def show_welcome(template):
    start_session()
    return render_template(template)


@app.route('/health', methods=['GET'])
def check_health():
    return json.dumps({'success': 'ok'})


@app.route('/search')
@mobile_template('{mobile/}search.html')
def show_search_places(template):
    return render_template(template)


@app.route('/stats/')
@basic_auth.required
def show_study_stats():
    stats = study.get_stats()
    return render_template('stats/stats.html', stats=stats)


@app.route('/stats/update')
@basic_auth.required
def study_stats_update():
    study.update_place_records()
    return json.dumps({"success": "ok"})


@app.route('/stats/users')
@basic_auth.required
def show_stats_users():
    stats = study.get_stats()
    return render_template('stats/users.html', page='users', stats=stats)


@app.route('/stats/pi')
@basic_auth.required
def show_stats_pi():
    return render_template('stats/pi.html', page='pi')


@app.route('/stats/models')
@basic_auth.required
def show_stats_models():
    models = study.get_model_stats()
    return render_template('stats/models.html', page='models', models=models)


@app.route('/stats/place')
@basic_auth.required
def show_stats_place():
    return render_template('stats/placeSearch.html', page='place')


@app.route('/stats/places')
@basic_auth.required
def show_stats_places():
    places = study.get_all_distinct_selected_places()
    return render_template('stats/places.html', page='places', places=places)


@app.route('/stats/placepi')
@basic_auth.required
def show_place_pi():
    place_id = request.args.get('place_id')
    place = foursquare.get_place(place_id)
    return render_template('stats/placePi.html', place=place)


@app.route('/stats/searchplace')
@app.route('/mobile/searchplace')
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


@app.route('/loadpi')
@mobile_template('{mobile/}loadPi.html')
def show_load_personal_information(template):
    return render_template(template)


@app.route('/stats/geocode')
@app.route('/geocode')
def search_geocode():
    query = request.args.get('query')
    return json.dumps(study.geocode_autocomplete(query))


@app.route('/getplacedetails')
def get_place_details():
    place_id = request.args.get('id')
    return json.dumps(foursquare.get_place(place_id))


@app.route('/piPlaces')
@mobile_template('{mobile/}piPlaces.html')
def show_personal_information(template):
    return render_template(template)


@app.route('/piTable')
def show_personal_information_table():
    return render_template('piTable.html')


@app.route('/piPrivacy')
@mobile_template('{mobile/}piPrivacy.html')
def show_personal_information_privacy(template):
    return render_template(template)


@app.route('/end')
@mobile_template('{mobile/}finish.html')
def show_end(template):
    study.end_session(session['sid'])
    print("End session %s" % session['sid'])
    return render_template(template)


# Logic to save the responses in the database
@app.route('/saveresponse')
def save_response():
    print("Save Response in database - Session id: %s / %s" % (session.get('sid', 'no session sid'), session.get('uid', 'no session uid')))
    print("Request: %s" % request.args)
    t = request.args.get('type')  # rel (relevance), pri (privacy), q1 (how well), q2 (how private)
    rating = request.args.get('r')
    if t == 'rel':
        pi_id = request.args.get('piid')
        place_id = request.args.get('pid')
        study.save_personal_information_relevance(session['sid'], place_id, pi_id, rating)
    elif t == 'imp':
        pi_id = request.args.get('piid')
        place_id = request.args.get('pid')
        study.save_personal_information_importance(session['sid'], place_id, pi_id, rating)
    elif t == 'pri':
        pi_id = request.args.get('piid')
        study.save_personal_information_privacy(session['sid'], pi_id, rating)
    elif t in ['q1', 'q2']:
        place_id = request.args.get('pid')
        study.save_place_question(session['sid'], place_id, t, rating)
    else:
        print("Unknown response type: %s" % t)
        return json.dumps({'success': 'ko'})

    return json.dumps({'success': 'ok'})


@app.route('/login')
def show_login():
    print("TrackingAdvisor login")

    if 'uid' not in session:
        # create a new session id
        session_id = "TrackingAdvisorLogin-" + utils.id_generator()
        print("created session-id: %s" % session_id)
        session['uid'] = session_id

        # create the login QR code
        utils.generate_qr_code(url=session_id,
                               logo_path="./static/img/location-arrow.svg",
                               output_file="./static/img/"+session_id+".svg")
    else:
        session_id = session['uid']
        print("used already-existing session-id: %s" % session_id)

    return render_template('login.html', qrcode=session_id+".svg")


@app.route('/getpi')
def get_personal_information():
    place_id = request.args.get('id')
    _ = foursquare.get_place(place_id)

    categories = foursquare.get_category_ids_for_venue(place_id)

    res_pis = []
    for category_id in categories['categories']:
        # get the personal information associated to the place category
        pis = personal_information.get_personal_information_from_foursquare_category(category_id)
        res_pis += pis

    return json.dumps(res_pis)


@app.route('/getuserplaces')
def get_authenticated_user_places():
    login = request.args.get('login')
    user_id = user_traces_db.get_user_id_from_temp_login(login)
    print("user_id: %s" % user_id)
    study.add_trackingadvisor_id(session['sid'], user_id)

    places = user_traces_db.load_all_foursquare_user_places(user_id)
    print("Got %s places" % places)

    return json.dumps(places)


@app.route('/getpis')
def get_personal_information_list():
    place_ids = request.args.getlist('ids[]')

    res = {}
    for place_id in place_ids:
        res_pis = []
        interests = foursquare.get_place_personal_information_aggregated_from_db(place_id)
        for ppi in interests:
            pi_id = ppi['pi_id']
            res_pis.append({
                'pi_id': pi_id,
                'pi_name': ppi['name'],
                'picid': ppi['category_id'],
                'category_icon': ppi['category_icon'],
                'rank_avg': float(ppi['rank_avg']),
                'nb': int(ppi['nb']),
                'score_avg': float(ppi['score_avg'])
            })

        res[place_id] = res_pis

    return json.dumps(res)


@app.route('/stats/computeplacepi')
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


@app.route('/stats/getplaceratings')
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

        progress = float(i)/nb_places
        socketio.emit('update', {'progress': progress, 'message': "%s" % place['name']}, namespace='/load', room=room)
        socketio.sleep(0.05)
        i += 1


# SocketIO
@socketio.on('connect')
def socket_connect_auth():
    print("SocketIO - Connection made to the server")
    pass


# SocketIO for the personal information loading screen

@socketio.on('mobile/update', namespace='/load')
@socketio.on('update', namespace='/load')
def socket_handle_update(data):
    room = str(session['sid'])
    socketio.start_background_task(target=compute_place_interests, room=room, places=data['places'])


@socketio.on('join_room', namespace='/load')
def socket_on_join():
    room = str(session['sid'])
    join_room(room)
    emit('join_room', {'room': room}, namespace='/load')


# SocketIO for the TrackingAdvisor Login screen

@socketio.on('join_room', namespace='/auth')
def socket_on_room_auth():
    room = str(session['uid'])
    join_room(room)
    emit('join_room', {'room': room}, namespace='/auth')
    print("SocketIO - Join room %s" % room)


if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=8000, debug=True)
