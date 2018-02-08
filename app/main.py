import os
import sys
import json
from flask import Flask, render_template, request
from flask_mail import Mail, Message
from werkzeug import secure_filename

import osm
import foursquare
import dbpedia
import db


UPLOAD_FOLDER = "./user_traces/"
TMP_UPLOAD_FOLDER = "./to_process/"

# create and configure the application object
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TMP_UPLOAD_FOLDER'] = TMP_UPLOAD_FOLDER
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'benji.baron@gmail.com'
app.config['MAIL_PASSWORD'] = 'dpgyuaqrldwolyyc'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
mail = Mail(app)


@app.route('/', methods=['GET'])
def root():
    return render_template('index.html')


@app.route('/getplaces', methods=['GET'])
def get_place():
    lon = float(request.args.get('lon'))
    lat = float(request.args.get('lat'))
    location = {"lon": lon, "lat": lat}

    res = dict()
    res["foursquare"] = {'type': 'points', 'result': foursquare.get_places(location, 50, 5)}
    res['osm-polygons'] = {'type': 'polygons', 'result': osm.get_polygons(location, 50)}
    res['dbpedia'] = {'type': 'points', 'result': dbpedia.get_places(location, 500, 5)}

    return json.dumps(res)


@app.route('/getfoursquareplace', methods=['GET'])
def get_foursquare_tips():
    venue_id = request.args.get('venue_id')
    res = foursquare.get_place(venue_id)

    return json.dumps(res)


@app.route('/mail', methods=['POST'])
def send_mail():
    msg = Message("[ISS-Semantica] Contact from user",
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
    print("register new user")
    return json.dumps({"success": "ok"})


@app.route('/userupdate', methods=['GET'])
def user_update():
    print("hello")
    user_id = request.args.get('userid')
    day = request.args.get('day')
    uu = db.get_day_user_update_from_db(user_id, day)
    return json.dumps(uu)


@app.route('/personalinformationcategories', methods=['GET'])
def personal_information_categories():
    pic = db.get_personal_information_categories()
    return json.dumps(pic)


@app.route('/userchallenge', methods=['GET'])
def user_challenge():
    user_id = request.args.get('userid')
    day = request.args.get('day')
    uu = db.get_user_review_challenge_from_db(user_id, day)
    return json.dumps(uu)


@app.route('/autocomplete', methods=['GET'])
def autocomplete_place():
    user_id = request.args.get('userid')
    lon = float(request.args.get('lon'))
    lat = float(request.args.get('lat'))
    query = request.args.get('query')
    location = {"lon": lon, "lat": lat}
    return json.dumps(foursquare.autocomplete_location(location, query))


@app.route('/rawtrace', methods=['GET'])
def raw_trace():
    user_id = request.args.get('userid')
    start = request.args.get('start')
    end = request.args.get('end')

    return json.dumps(db.get_raw_trace(user_id, start, end))


@app.route('/addvisit', methods=['POST'])
def add_visit():
    visit_update = {
        "user_id": request.json['userid'],
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

    print(visit_update)

    t = request.json['type']
    if t == 0:  # add place
        return json.dumps(db.add_visit(visit_update))
    elif t == 1:  # edit place
        return json.dumps(db.update_visit(visit_update))


@app.route('/consentform', methods=['GET'])
def consent_form():
    return json.dumps(db.get_consent_form())


@app.route('/uploader', methods=['POST'])
def upload_file():
    try:
        f = request.files['trace']
        filename = secure_filename(f.filename)

        # save the file in a temporary folder
        path = os.path.join(app.config['TMP_UPLOAD_FOLDER'], filename)
        f.save(path)
        print("saved file %s in %s" % (filename, path))

        return json.dumps({"success": "ok"})
    except:
        return json.dumps({"failure": "ko"})


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, port=80)