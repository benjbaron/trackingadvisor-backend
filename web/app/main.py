import os
import os.path
import sys
import json
import uuid
import time
from gevent import monkey
from flask import Flask, render_template, request, session, send_file, url_for
from flask_mail import Mail, Message
from flask_basicauth import BasicAuth
from flask_socketio import SocketIO, join_room
from werkzeug import secure_filename

import db
import utils
import foursquare
import user_traces_db
import personal_information
import notifications

monkey.patch_socket()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'TraCkIngADviSoR'
app.config['BASIC_AUTH_USERNAME'] = 'trackingadvisor'
app.config['BASIC_AUTH_PASSWORD'] = 'trackingadvisor-iss'

basic_auth = BasicAuth(app)
socketio = SocketIO(app, message_queue="amqp://colossus07/socketio", async_mode='gevent_uwsgi')


@app.route('/survey', methods=['GET'])
def show_survey():
    print("show survey")
    session_id = ""
    if 'uid' not in session:
        # create a new session id
        session_id = "TrackingAdvisorSurvey-" + utils.id_generator()
        print("created session-id: %s" % session_id)
        session['uid'] = session_id

    else:
        session_id = session['uid']
        print("used already-existing session-id: %s" % session_id)

    return render_template('survey.html')


@app.route('/', methods=['GET'])
@app.route('/login/', methods=['GET'])
def login():
    print("login")
    session_id = ""
    fname = "./static/img/"+session_id+".svg"
    if 'uid' not in session or not os.path.isfile(fname):
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


@app.route('/health', methods=['GET'])
def check_health():
    return json.dumps({'success': 'ok'})


@app.route('/qrcode', methods=['GET'])
def generate_qrcode():
    text = request.args.get('text')

    print("text: \"%s\"" % text)
    # create the login QR code
    session_id = "TrackingAdvisorQRCode-" + utils.id_generator()
    qrcode_filename = "qrcode-" + session_id + ".svg"
    utils.generate_qr_code(url=text,
                           logo_path="./static/img/location-arrow.svg",
                           output_file="./static/img/" + qrcode_filename)

    return render_template('qrcode.html', qrcode=qrcode_filename)


@socketio.on('connect')
def socket_connect():
    print("Connection made to the server")
    pass


@socketio.on('join_room', namespace='/auth')
def on_room():
    room = str(session['uid'])
    join_room(room)


@app.route('/admin/')
@basic_auth.required
def admin_home():
    users = db.get_all_users()
    stats = db.get_basic_stats(users)
    return render_template('admin/admin.html', users=users, stats=stats)


@app.route('/admin/dashboard')
@basic_auth.required
def admin_dashboard():
    start_time = time.time()
    users = db.get_all_users()
    end_time = time.time()
    print("elapsed time (1): %s" % (end_time - start_time))

    start_time = time.time()
    stats = db.get_basic_stats(users)
    end_time = time.time()
    print("elapsed time (2): %s" % (end_time - start_time))
    return render_template('admin/dashboard.html', page='dashboard', users=users, stats=stats)


@app.route('/admin/map')
@basic_auth.required
def admin_map():
    start_time = time.time()
    visits = db.get_all_visits_anonymous_geojson()
    end_time = time.time()
    print("elapsed time (1): %s" % (end_time - start_time))

    start_time = time.time()
    users = dict((u['user_id'], u) for u in db.get_all_users())
    end_time = time.time()
    print("elapsed time (2): %s" % (end_time - start_time))
    return render_template('admin/map.html', page='map', visits=visits, users=users)


@app.route('/admin/pi')
@basic_auth.required
def admin_personal_information():
    pis = foursquare.get_all_personal_information()
    pis_categories = list([{'name': e[0], 'icon': e[1]} for e in set([(pi['category_id'], pi['category_icon']) for pi in pis if pi['category_id'] != ''])])
    pis_subcategories = list([{'name': e[0], 'icon': e[1]} for e in set([(pi['subcategory_name'], pi['subcategory_icon']) for pi in pis if pi['subcategory_name'] != ''])])
    return render_template('admin/pi.html', page='pi', pis=pis, categories=pis_categories, subcategories=pis_subcategories)


@app.route('/admin/chat')
@basic_auth.required
def admin_chat():
    # get users who used the chat
    users = user_traces_db.load_all_users_with_messages()
    return render_template('admin/chat.html', page='chat', users=users)


@app.route('/admin/chatmessages')
@basic_auth.required
def admin_chat_messages():
    user_id = request.args.get('userid')
    messages = user_traces_db.load_user_all_messages(user_id)
    return render_template('admin/chat-messages.html', messages=messages)


@app.route('/admin/sendmessage', methods=['GET'])
@basic_auth.required
def send_message():
    user_id = request.args.get('userid')
    ts = request.args.get('timestamp')
    message = request.args.get('message')
    ts_utc = int(float(ts))
    ts_local = int(float(ts))
    print(ts, ts_local, ts_utc, ts_utc - ts_local)
    msg = {
        'user_id': user_id,
        'message': message,
        'sender': request.args.get('sender', True),
        'timestamp': ts_utc,
        'utc_offset': ts_utc - ts_local
    }
    user_traces_db.save_user_message_to_db(msg)
    # notify the phone
    notifications.send_push_notification(user_id, 'message', "You received a new message", args=msg, use_sandbox=True)
    notifications.send_push_notification(user_id, 'message', "You received a new message", args=msg, use_sandbox=False)

    return json.dumps({"success": "ok"})


@app.route('/admin/picollapsed')
@basic_auth.required
def admin_personal_information_collapsed():
    category_id = request.args.get('catid')
    print("showing for category %s" % category_id)

    # get the topics associated to the place category
    topics = personal_information.get_foursquare_category_topics(category_id)

    # get the personal information associated to the place category
    pis = personal_information.get_personal_information_from_foursquare_category(category_id)
    pis_str = ["%s %s" % (pi['picid'], pi['pi_name']) for pi in pis]
    print("pis: %s" % pis_str)

    print("number of personal information: %s, number of topics: %s" % (len(topics), len(pis)))

    return render_template('admin/pi-collapsed.html', topics=topics, pis=pis_str, category_id=category_id)


@app.route('/admin/updatepi')
@basic_auth.required
def admin_update_personal_information():
    category_id = request.args.get('catid')
    pi_id = request.args.get('piid')
    t = request.args.get('type')
    if t == 'create':
        personal_information.create_or_update_foursquare_category_personal_information(category_id, pi_id)
    elif t == 'remove':
        personal_information.remove_personal_information_from_foursquare_category(category_id, pi_id)
    elif t == 'edit':
        print("edit personal information")

    return json.dumps({"status": "ok"})


@app.route('/admin/addpi')
@basic_auth.required
def admin_add_personal_information():
    name = request.args.get('name')
    picid = request.args.get('cat')

    if name == '' or picid == '':
        return json.dumps({})

    pi = {
        "name": name,
        "picid": picid,
        "category_icon": request.args.get('catimg', ''),
        "subcategory_name": request.args.get('subcat', ''),
        "subcategory_icon": request.args.get('subcatimg', '')
    }
    print("request: {}".format(pi))
    personal_information.add_personal_information(pi)

    # update the personal information
    if pi['subcategory_icon'] != '':
        pi['icon'] = url_for('static', filename='img/icons/' + pi['subcategory_icon'] + '.svg')
    elif pi['category_icon'] != '':
        pi['icon'] = url_for('static', filename='img/icons/' + pi['category_icon'] + '.svg')

    return json.dumps(pi)


@app.route('/admin/places')
@basic_auth.required
def admin_places():
    return render_template('admin/places.html', page='places')


@app.route('/admin/getplaces')
@basic_auth.required
def admin_get_places():
    print(request.args)
    neLat = request.args.get('neLat')
    neLng = request.args.get('neLng')
    swLat = request.args.get('swLat')
    swLng = request.args.get('swLng')
    places = foursquare.get_places_within_bounding_box(neLat, neLng, swLat, swLng)
    return json.dumps(places)


@app.route('/admin/placecategories')
@basic_auth.required
def admin_place_categories():
    categories = foursquare.get_all_categories_with_personal_information()
    pis = personal_information.get_all_personal_information()
    return render_template('admin/place-categories.html', page='placecategories', categories=categories, pis=pis)


@app.route('/user/<login>')
def show_user_profile(login):
    if 'authenticated' in request.args:
        user_id = user_traces_db.get_user_id_from_temp_login(login)
        print("user_id: %s" % user_id)
        return render_template('user.html', login=login, authenticated=True, exists=(user_id is not None))
    else:
        user_id = user_traces_db.get_user_id_from_temp_login(login)
        user = user_traces_db.get_all_info_user(user_id)
        return render_template('user.html', login=login, user=user, authenticated=False, exists=(user_id is not None))


@app.route('/user/<login>/dashboard')
def show_user_dashboard(login):
    user_id = user_traces_db.get_user_id_from_temp_login(login)
    user = user_traces_db.get_all_info_user(user_id)
    print("user_id: %s, user info: %s" % (user_id, user))
    return render_template('dashboard.html', login=login, page='dashboard', user=user)


@app.route('/user/<login>/map')
def show_user_map(login):
    user_id = user_traces_db.get_user_id_from_temp_login(login)
    visits = db.get_all_visits_user_geojson(user_id)
    user = user_traces_db.get_all_info_user(user_id)
    print("user_id: %s, number of visits: %s" % (user_id, len(visits)))
    return render_template('map.html', login=login, visits=visits, user=user, page='map')


@app.route('/user/<login>/modal')
def show_user_modal(login):
    user_id = user_traces_db.get_user_id_from_temp_login(login)
    print("show modal for login %s" % login)
    return render_template('export-modal.html', login=login)


@app.route("/signout")
def sign_out():
    login = request.args.get('login')
    user_id = user_traces_db.get_user_id_from_temp_login(login)
    user_traces_db.create_temp_login(user_id, "")
    print("sign out with login: %s" % login)
    return json.dumps({"status": "ok"})


@app.route('/user/<login>/export')
def export_user_data(login):
    user_id = user_traces_db.get_user_id_from_temp_login(login)
    zipfile = db.export_user_data(user_id)
    print("send zipfile %s" % zipfile)
    return send_file(zipfile, as_attachment=True)


@app.route('/rawtrace')
def raw_trace():
    user_id = ""
    if 'login' in request.args:
        login = request.args.get('login')
        user_id = user_traces_db.get_user_id_from_temp_login(login)
    elif 'userid' in request.args:
        user_id = request.args.get('userid')

    if 'day' in request.args:
        day = request.args.get('day')
        start = utils.start_of_day_str(day)
        end = utils.end_of_day_str(day)

        return json.dumps(db.get_raw_trace(user_id, start, end, type=request.args.get('type'), utc=False))

    start = request.args.get('start')
    end = request.args.get('end')

    return json.dumps(db.get_raw_trace(user_id, start, end, type=request.args.get('type'), utc=True))


@app.route('/fulltrace')
def full_trace():
    user_id = ""
    if 'login' in request.args:
        login = request.args.get('login')
        user_id = user_traces_db.get_user_id_from_temp_login(login)
    elif 'userid' in request.args:
        user_id = request.args.get('userid')

    if 'day' in request.args:
        day = request.args.get('day')
        start = utils.start_of_day_str(day)
        end = utils.end_of_day_str(day)

        raw_trace = db.get_raw_trace(user_id, start, end, type=request.args.get('type'), utc=False)
        raw_visits = db.get_raw_visits(user_id, day, type=request.args.get('type'))

        return json.dumps({"points": raw_trace, "visits": raw_visits})
    return json.dumps({})


if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', debug=False, port=8000)

