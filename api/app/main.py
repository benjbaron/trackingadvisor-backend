import os
import sys
import time
import json
import requests
import uwsgi
from flask import Flask, render_template, request
from flask_mail import Mail, Message
from flask_socketio import SocketIO
from werkzeug import secure_filename
from raven import Client
from raven.contrib.flask import Sentry

import osm
import foursquare
import dbpedia
import db
import utils
import user_traces_db

UPLOAD_FOLDER = "./user_traces/"
TMP_UPLOAD_FOLDER = "./to_process/"
MAG_FILES_UPLOAD_FOLDER = "./magfiles/"

# create and configure the application object
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TMP_UPLOAD_FOLDER'] = TMP_UPLOAD_FOLDER
app.config['MAG_FILES_UPLOAD_FOLDER'] = MAG_FILES_UPLOAD_FOLDER
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'benji.baron@gmail.com'
app.config['MAIL_PASSWORD'] = 'dpgyuaqrldwolyyc'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['SECRET_KEY'] = '12345'
mail = Mail(app)

socketio = SocketIO(message_queue="amqp://colossus07/socketio")
client = Client('https://8f77b4f7e5a6410194f5826deaa3f9f4:74d1d77376ea4f7f8785cb192e62daeb@sentry.io/1207941')
sentry = Sentry(app, dsn='https://8f77b4f7e5a6410194f5826deaa3f9f4:74d1d77376ea4f7f8785cb192e62daeb@sentry.io/1207941')


@app.route('/health', methods=['GET'])
def check_health():
    return json.dumps({'success': 'ok'})


@app.route('/authclient', methods=['GET'])
def auth_client():
    room = request.args.get('text')
    user_id = request.args.get('userid')

    temp_login = ""
    res = user_traces_db.get_temp_login_from_user_id(user_id)
    if not res['temp_login'] or (res['temp_login_created'] and (time.time() - res['temp_login_created'] > 3600)):
        print("create a new temp login")
        # create a temporary user login
        temp_login = utils.id_generator()
        user_traces_db.create_temp_login(user_id, temp_login)
        print("\ttemp login: %s" % temp_login)
    else:
        temp_login = res['temp_login']
        print("got already-existing temp login %s" % temp_login)

    # forward this request to the client directly using socketio
    r = {
        "login": temp_login,
        "date": request.args.get('date')
    }

    print("received: %s" % r)

    print("emit socketio message to /auth namespace")
    socketio.emit("authclientrequest", r, namespace='/auth', room=room)

    return json.dumps({"status": "ok", "code": temp_login})


@app.route('/', methods=['GET'])
def root():
    return render_template('index.html')


@app.route('/sendmessage', methods=['GET'])
def send_message():
    print(request.args)
    ts = request.args.get('timestamp')
    if utils.is_number(ts):
        ts_utc = int(float(ts))
        ts_local = int(float(ts))
    else:
        ts_local = user_traces_db.timestamp_from_string(ts)
        ts_utc = user_traces_db.timestamp_utc_from_string(ts)
    print(ts, ts_local, ts_utc, ts_utc - ts_local)
    msg = {
        'user_id': request.args.get('userid'),
        'message': request.args.get('message'),
        'sender': request.args.get('sender', True),
        'timestamp': ts_utc,
        'utc_offset': ts_utc - ts_local
    }
    user_traces_db.save_user_message_to_db(msg)
    return json.dumps({"success": "ok"})


@app.route('/getmessages', methods=['GET'])
def get_messages():
    user_id = request.args.get('userid')
    messages = user_traces_db.load_user_all_messages(user_id)
    print(messages)

    return json.dumps(messages)


@app.route('/getplaces', methods=['GET'])
def get_place():
    lon = float(request.args.get('lon'))
    lat = float(request.args.get('lat'))
    distance = float(request.args.get('distance', default=50))
    limit = float(request.args.get('limit', default=5))
    location = {"lon": lon, "lat": lat}

    res = dict()
    res["foursquare"] = {'type': 'points', 'result': foursquare.get_places(location, distance, limit)}
    # res['osm-polygons'] = {'type': 'polygons', 'result': osm.get_polygons(location, 50)}
    # res['dbpedia'] = {'type': 'points', 'result': dbpedia.get_places(location, 500, 5)}

    return json.dumps(res)


@app.route('/getclosestplace', methods=['GET'])
def get_closest_place():
    lon = float(request.args.get('lon'))
    lat = float(request.args.get('lat'))
    user_id = request.args.get('userid')
    location = {"lon": lon, "lat": lat}

    place = db.closest_place(user_id, location)
    print("closest place from (%s, %s) for %s: %s %s" % (lon, lat, user_id, place['emoji'], place['name']))

    return json.dumps(db.closest_place(user_id, location))


@app.route('/getfoursquareplace', methods=['GET'])
def get_foursquare_tips():
    venue_id = request.args.get('venue_id')
    res = foursquare.get_place(venue_id)

    return json.dumps(res)


@app.route('/optout', methods=['POST'])
def opt_out():
    user_id = request.json['userid']
    print("user %s opt-out request" % user_id)
    # TODO: Remove all user data for user_id
    return json.dumps({"status": "ok"})


@app.route('/aggregatepersonalinformation', methods=['GET'])
def aggregated_personal_information():
    try:
        user_id = request.args.get('userid')
        return json.dumps(db.get_aggregated_personal_information(user_id))
    except:
        client.captureException()


@app.route('/mail', methods=['POST'])
def send_mail():
    msg = Message("[TrackingAdvisor] Contact from user",
        sender="iss-semantica@geog.ucl.ac.uk",
        recipients=["b.baron@ucl.ac.uk"],
        cc=[request.json['email']]
    )
    msg.html = "<h2>Message from {}</h2>".format(request.json['name'])
    msg.html += """<b>Name:</b> {name}</br>
    <b>Email:</b> {email}</br>
    <b>UUID:</b> {uuid}</br>
    <b>Device type:</b> {device}</br>
    <b>System version:</b> {version}</br>
    <b>Reason:</b> {reason}</br>
    <p>{message}</p>""".format(name=request.json['name'],
                               email=request.json['email'],
                               uuid=request.json['uuid'],
                               device=request.json['device'],
                               version=request.json['version'],
                               reason=request.json['reason'],
                               message=request.json['message'])
    mail.send(msg)
    return json.dumps({"success": "ok"})


@app.route('/register', methods=['POST'])
def register_new_user():
    try:
        print("register new user")
        uuid = request.json['uuid']
        push_notification_id = request.json['pushnotificationid']
        date = request.json['date']
        type = request.json['type']
        user_id = db.register_user(type, date, uuid, push_notification_id)
        return json.dumps({"userid": user_id})
    except:
        client.captureException()


@app.route('/updateuserinfo', methods=['POST'])
def update_user_info():
    try:
        print("update user information")
        user_id = request.json['userid']
        uuid = request.json['uuid']
        push_notification_id = request.json['pushnotificationid']
        date = request.json['date']
        type = request.json['type']
        db.update_user_information(user_id, type, uuid, push_notification_id)

        return json.dumps({})
    except:
        client.captureException()


@app.route('/userupdate', methods=['GET'])
def user_update():
    try:
        print(request.args)
        user_id = request.args.get('userid')
        days = request.args.getlist('days[]')
        print(days)
        uu = db.get_day_user_update_from_db(user_id, days)
        return json.dumps(uu)
    except:
        client.captureException()


@app.route('/personalinformationcategories', methods=['GET'])
def personal_information_categories():
    pic = db.get_personal_information_categories()
    return json.dumps(pic)


@app.route('/recordingplaces', methods=['GET'])
def recording_places():
    places = db.get_recording_places()
    return json.dumps(places)


@app.route('/userchallenge', methods=['GET'])
def user_challenge():
    user_id = request.args.get('userid')
    day = request.args.get('day')
    uu = db.get_user_review_challenge_from_db(user_id, day)
    return json.dumps(uu)


@app.route('/userchallengeupdate', methods=['POST'])
def user_challenge_update():
    user_id = request.json['userid']
    review_challenges = request.json['reviewchallenges']
    db.update_user_review_challenge_from_db(user_id, review_challenges)
    return json.dumps({})


@app.route('/autocomplete', methods=['GET'])
def autocomplete_place():
    user_id = request.args.get('userid')
    lon = float(request.args.get('lon'))
    lat = float(request.args.get('lat'))
    query = request.args.get('query', '').lower()
    req_type = request.args.get('type', 'es')
    location = {"lon": lon, "lat": lat}
    return json.dumps(db.autocomplete_location(user_id, location, query, req_type))


@app.route('/autocompletepi', methods=['GET'])
def autocomplete_pi():
    try:
        user_id = request.args.get('userid')
        category = request.args.get('cat')
        return json.dumps(db.autocomplete_personal_information(user_id, category))
    except:
        print("Unexpected error:", sys.exc_info()[0])
        client.captureException()


@app.route('/personalinformationupdate', methods=['POST'])
def personal_information_update():
    try:
        t = request.json['t']
        if t == 0:  # add a new personal information
            pi = {
                'user_id': request.json['userid'],
                'place_id': request.json['pid'],
                'category_id': request.json['picid'],
                'name': utils.title_except(request.json['name']),
                'rating': 3,  # Yes!
                'explanation': 'You entered this personal information',
                'source': ['user']
            }

            return json.dumps(db.add_personal_information(pi))
        elif t == 1:  # add personal information comment
            pi = {
                'user_id': request.json['userid'],
                'pi_id': request.json['piid'],
                'explanation_comment': request.json['comment']
            }
            return json.dumps(db.update_personal_information(pi))
    except:
        client.captureException()


@app.route('/rawtrace', methods=['GET'])
def raw_trace():
    try:
        user_id = request.args.get('userid')

        if 'day' in request.args:
            day = request.args.get('day')
            start = utils.start_of_day_str(day)
            end = utils.end_of_day_str(day)

            return json.dumps(db.get_raw_trace(user_id, start, end, type=request.args.get('type'), utc=False))

        start = request.args.get('start')
        end = request.args.get('end')

        return json.dumps(db.get_raw_trace(user_id, start, end, type=request.args.get('type'), utc=True))
    except:
        client.captureException()


@app.route('/addvisit', methods=['POST'])
def add_visit():
    try:
        visit_update = {}
        t = request.json['type']
        user_id = request.json['userid']

        print("[%s] [add visit] type %s" % (user_id, t, ))
        if t in [0, 1]:
            visit_update = {
                "user_id": user_id,
                "venue_id": request.json['venueid'],
                "day": request.json['day'],
                "arrival": request.json['start'],
                "departure": request.json['end'],
                "lon": request.json['lon'],
                "lat": request.json['lat'],
                "name": request.json['name'],
                "address": request.json['address'],
                "city": request.json['city'],
                "visit_id": request.json['visitid'],
                "old_place_id": request.json['oldplaceid'],
                "new_place_id": request.json['newplaceid']
            }
        elif t in [2, 3]:
            visit_update = {
                "user_id": user_id,
                "visit_id": request.json['visitid']
            }
        elif t == 4:
            visit_update = {
                "user_id": user_id,
                "place_id": request.json['placeid'],
                "place_type": request.json['placetype']
            }
        elif t == 5:
            visit_update = {
                "user_id": user_id,
                "place_id": request.json['placeid'],
                "name": request.json['name'],
                "address": request.json['address'],
                "city": request.json['city']
            }

        print("visit update: %s" % visit_update)

        if t == 0:    # add place
            return json.dumps(db.add_visit(visit_update))
        elif t == 1:  # edit place
            return json.dumps(db.update_visit(visit_update))
        elif t == 2:  # delete place
            return json.dumps(db.delete_visit(visit_update))
        elif t == 3:  # visited place
            return json.dumps(db.update_visit_visited(visit_update))
        elif t == 4:  # changed place type
            return json.dumps(db.update_place_type(visit_update))
        elif t == 5:  # changed place name and address
            return json.dumps(db.update_place(visit_update))
    except:
        client.captureException()


@app.route('/consentform', methods=['GET'])
def consent_form():
    try:
        return json.dumps(db.get_consent_form())
    except:
        client.captureException()


@app.route('/terms', methods=['GET'])
def terms():
    try:
        return json.dumps(db.get_text('supp/terms.csv'))
    except:
        client.captureException()


@app.route('/privacypolicy', methods=['GET'])
def privacy_policy():
    try:
        return json.dumps(db.get_text('supp/privacy_policy.csv'))
    except:
        client.captureException()


@app.route('/reviews', methods=['POST'])
def reviews():
    try:
        print(request.json)
        user_id = request.json['userid']
        reviews = request.json['reviews']
        db.update_reviews(reviews, user_id)
        return json.dumps({})
    except:
        client.captureException()


@app.route('/personalinformationreviews', methods=['POST'])
def personal_information_reviews():
    try:
        user_id = request.json['userid']
        reviews = request.json['reviews']

        return json.dumps(db.save_aggregated_personal_information_reviews(user_id, reviews))
    except:
        client.captureException()
        return json.dumps({})


@app.route('/uploader', methods=['POST'])
def upload_file():
    print("files: %s" % request.files)
    try:
        # save the trace file
        if 'trace' in request.files:
            f = request.files['trace']
            filename = secure_filename(f.filename)

            # save the trace file in a temporary folder
            path = os.path.join(app.config['TMP_UPLOAD_FOLDER'], filename)
            f.save(path)

            print("sending message...")

            db.send_incoming_message_to_queue(filename)
            print("saved file %s in %s" % (filename, path))

        # save the log file
        if 'log' in request.files:
            f_log = request.files['log']
            filename_log = secure_filename(f_log.filename)

            # save the log file in a temporary folder
            path_log = os.path.join(app.config['TMP_UPLOAD_FOLDER'], filename_log)
            f_log.save(path_log)
            print("saved log file %s in %s" % (filename_log, path_log))
        
        # save the pedometer file
        if 'pedometer' in request.files:
            f_ped = request.files['pedometer']
            filename_ped = secure_filename(f_ped.filename)

            # save the log file in a temporary folder
            path_ped = os.path.join(app.config['TMP_UPLOAD_FOLDER'], filename_ped)
            f_ped.save(path_ped)
            print("saved pedometer file %s in %s" % (filename_ped, path_ped))

        return json.dumps({"success": "ok"})
    except:
        client.captureException()
        return json.dumps({"failure": "ko"})


@app.route('/uploadloc', methods=['POST'])
@app.route('/uploadmag', methods=['POST'])
def upload_mag_file():
    print("upload mag")
    print(request.files['trace'])
    try:
        f = request.files['trace']
        filename = secure_filename(f.filename)

        # save the file in a temporary folder
        path = os.path.join(app.config['MAG_FILES_UPLOAD_FOLDER'], filename)
        f.save(path)
        print("saved file %s in %s" % (filename, path))

        return json.dumps({"success": "ok"})
    except:
        client.captureException()
        return json.dumps({"failure": "ko"})


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, port=8000)

