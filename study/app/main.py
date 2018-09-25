import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, session, send_file, url_for
from flask_socketio import SocketIO, emit, send, join_room

import os
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
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]

        scheme = environ.get('HTTP_X_SCHEME', '')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
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
app.wsgi_app = ReverseProxied(app.wsgi_app)
socketio = SocketIO(app, message_queue="amqp://colossus07/socketio")

BASE_URL = "https://api.foursquare.com/v2/"

# getting the database connection information
connection = None
cursor = None


def get_ip_address(request):
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in ip_address:
        ip_address = ip_address.split(',')[0].strip()

    return ip_address


def get_db_connection():
    global cursor, connection
    if cursor is None or connection is None:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)

    # Test the liveliness of the connection.
    try:
        cursor.execute("SELECT 1")
    except psycopg2.InterfaceError:
        connection, cursor = utils.connect_to_db("foursquare", cursor_type=psycopg2.extras.DictCursor)


def get_places(query, location, bounds, limit=50):
    get_db_connection()

    url = BASE_URL
    url += "venues/search"
    params = {
        "ne": "%s,%s" % (bounds['ne']['lat'], bounds['ne']['lon']),
        "sw": "%s,%s" % (bounds['sw']['lat'], bounds['sw']['lon']),
        "limit": str(limit),
        "query": query,
        "intent": "browse"
    }

    data = foursquare.send_request(url, params)
    results = []

    if data is None or 'response' not in data or 'venues' not in data['response']:
        return results

    for venue in data['response']['venues']:
        venue_id = venue['id']
        address = "%s, " % venue['location']['address'] if 'address' in venue['location'] else ''
        address += venue['location']['city'] if 'city' in venue['location'] else ''
        categories = [c for c in venue['categories'] if c['primary']]
        category = {}
        if len(categories) > 0:
            category = categories[0]
            emoji, icon = foursquare.get_icon_for_venue(venue_id, {'categories': [category['id']]}, connection=connection, cursor=cursor)
        else:
            emoji, icon = '👣', 'map-marker'

        res = {
            'address': address,
            'category': category.get('name', ''),
            'lat': venue['location']['lat'],
            'lon': venue['location']['lng'],
            'name': venue['name'],
            'id': venue_id,
            'icon': icon
        }

        results.append(res)

    return results


def geocode_autocomplete(query):
    url = BASE_URL
    url += "geo/geocode"
    params = {
        "autocomplete": "true",
        "allowCountry": "false",
        "maxInterpretations": "10",
        "locale": "en",
        "explicit-lang": "true",
        "query": query
    }

    data = foursquare.send_request(url, params)
    results = []

    if 'response' not in data or 'geocode' not in data['response']:
        return results

    if 'interpretations' not in data['response']['geocode']:
        return results

    if 'items' not in data['response']['geocode']['interpretations']:
        return results

    for geo in data['response']['geocode']['interpretations']['items']:
        results.append({
            "name": geo['feature']['displayName'],
            "id": geo['feature']['id'],
            "geometry": geo['feature']['geometry']
        })

    return results


@app.route('/', methods=['GET', 'POST'])
def show_welcome():
    # create a new session
    if 'sid' not in session:
        session_id = "SemanticaStudy-" + utils.id_generator()
        print("created session-id: %s" % session_id)
        session['sid'] = session_id
    else:
        session_id = session['sid']
        print("using session-id: %s" % session_id)

    study.start_session(session_id, get_ip_address(request))
    return render_template('welcome.html')


@app.route('/health', methods=['GET'])
def check_health():
    return json.dumps({'success': 'ok'})


@app.route('/search')
def show_search_places():
    return render_template('search.html')


@app.route('/placesearch')
def show_place_search():
    return render_template('placeSearch.html')


@app.route('/placepi')
def show_place_pi():
    place_id = request.args.get('place_id')
    place = foursquare.get_place(place_id)
    return render_template('placePi.html', place=place)


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

    return json.dumps(get_places(query, location, bounds))


@app.route('/location')
def get_location():
    ip_address = get_ip_address(request)

    key = random.choice(keys.IPSTACK_KEYS)
    send_url = 'http://api.ipstack.com/%s?access_key=%s' % (ip_address, key)
    r = requests.get(send_url).json()

    return json.dumps({'lat': r['latitude'], 'lon': r['longitude']})


@app.route('/loadpi')
def show_load_personal_information():
    return render_template('loadPi.html')


@app.route('/geocode')
def search_geocode():
    query = request.args.get('query')
    return json.dumps(geocode_autocomplete(query))


@app.route('/getplacedetails')
def get_place_details():
    place_id = request.args.get('id')
    return json.dumps(foursquare.get_place(place_id))


@app.route('/pi')
def show_personal_information():
    return render_template('piCards.html')


@app.route('/piTable')
def show_personal_information_table():
    return render_template('piTable.html')


@app.route('/piPrivacy')
def show_personal_information_privacy():
    return render_template('piPrivacy.html')


@app.route('/end')
def show_end():
    study.end_session(session['sid'])
    print("End session %s" % session['sid'])
    return render_template('finish.html')


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


def compute_place_interests(room, places):
    print(" [x] Instantiating a RPC client")
    worker_rpc = WorkerRpcClient()

    socketio.emit('update', {'progress': 0, 'message': "Processing"}, namespace='/load', room=room)
    socketio.sleep(0.05)

    i = 1
    nb_places = len(places)
    for place_id, place in places.items():
        study.save_place(room, place_id, place['name'])
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
