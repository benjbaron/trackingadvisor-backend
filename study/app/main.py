from flask import Flask, render_template, request, session, send_file, url_for
from flask_socketio import SocketIO, emit, send, join_room
import eventlet

import json
import requests
import random


import foursquare
import keys
import utils
import personal_information

# monkey.patch_all()

# monkey.patch_socket()


# http://flask.pocoo.org/snippets/35/
class ReverseProxied(object):
    '''Wrap the application in this middleware and configure the
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

    :param app: the WSGI application
    '''
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


app = Flask(__name__)
app.config['SECRET_KEY'] = 'seManTiCa'
app.wsgi_app = ReverseProxied(app.wsgi_app)
socketio = SocketIO(app, logger=True)

BASE_URL = "https://api.foursquare.com/v2/"


def get_places(query, location, bounds, limit=50):
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

    if 'response' not in data or 'venues' not in data['response']:
        return results

    for venue in data['response']['venues']:
        venue_id = venue['id']
        address = "%s, " % venue['location']['address'] if 'address' in venue['location'] else ''
        address += venue['location']['city'] if 'city' in venue['location'] else ''
        categories = [c for c in venue['categories'] if c['primary']]
        category = {}
        if len(categories) > 0:
            category = categories[0]
            emoji, icon = foursquare.get_icon_for_venue(venue_id, {'categories': [category['id']]})
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


@app.route('/', methods=['GET', 'POST'])
def show_welcome():
    return render_template('welcome.html')


@app.route('/search')
def show_search_places():
    return render_template('search.html')


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
    ip_address = request.remote_addr
    key = random.choice(keys.IPSTACK_KEYS)
    send_url = 'http://api.ipstack.com/%s?access_key=%s' % (ip_address, key)
    r = requests.get(send_url).json()

    return json.dumps({'lat': r['latitude'], 'lon': r['longitude']})


@app.route('/loadpi')
def show_load_personal_information():
    # create a new session id
    session_id = "SemanticaStudy-" + utils.id_generator()
    print("created session-id: %s" % session_id)
    session['uid'] = session_id

    return render_template('loadpi.html')


@app.route('/pi')
def show_personal_information():
    # create a new session id
    return render_template('pi.html')


@app.route('/end')
def show_end():
    return render_template('finish.html')


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


@app.route('/getpis')
def get_personal_information_list():
    print(request.args)
    place_ids = request.args.getlist('ids[]')
    print(place_ids)

    res = {}
    for place_id in place_ids:
        categories = foursquare.get_category_ids_for_venue(place_id)

        res_pis = {}
        for category_id in categories['categories']:
            # get the personal information associated to the place category
            pis = personal_information.get_personal_information_from_foursquare_category(category_id)
            for pi in pis:
                res_pis[pi['pi_id']] = pi

        res[place_id] = res_pis

    return json.dumps(res)


def background_thread(room, places):
    i = 1
    for place_id, place in places.items():
        _ = foursquare.get_place(place_id)
        progress = float(i)/len(places)
        socketio.emit('update', {'progress': progress, 'message': "%s" % place['name']}, namespace='/load', room=room)
        socketio.sleep(0.25)
        i += 1


@socketio.on('update', namespace='/load')
def socket_handle_update(data):
    room = str(session['uid'])
    socketio.start_background_task(target=background_thread, room=room, places=data['places'])


@socketio.on('connect', namespace='/load')
def socket_connect():
    pass


@socketio.on('join_room', namespace='/load')
def socket_on_join():
    room = str(session['uid'])
    join_room(room)
    emit('join_room', {'room': room})


if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=8000)
