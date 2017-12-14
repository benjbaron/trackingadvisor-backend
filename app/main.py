from flask import Flask, render_template, request
from flask_mail import Mail, Message

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


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True, port=80)