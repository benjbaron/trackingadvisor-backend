import requests
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from gmail_info import fromaddr, username, password, SERVICES


def now():
    return datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')


def send_email(subject, message, to):
    """
    Sends an email with the specified subject and message to the given recipient.
    See: https://stackoverflow.com/questions/882712/sending-html-email-using-python
         https://stackoverflow.com/questions/10147455/how-to-send-an-email-with-gmail-as-provider-using-python

    :param subject: Subject of the email to send.
    :param s: message string of the message to send in the email.
    :param to: recipient of the message.
    :return: Nothing.
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = fromaddr
    msg['To'] = to

    text = "Time: %s\n\nMessage:\n\n%s" % (now(), message)
    html = """\
    <html>
      <head></head>
      <body>
        <p><b>Time:</b> {0}<br/><br/>
           <b>Message:</b><br/>
           {1}
        </p>
      </body>
    </html>
    """.format(now(), message)

    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(part1)
    msg.attach(part2)

    server = smtplib.SMTP('smtp.gmail.com:587')
    server.ehlo()
    server.starttls()
    server.login(username, password)
    server.sendmail(fromaddr, to, msg.as_string())
    server.quit()


for url, service, to in SERVICES:
    print("test %s" % service)
    # check the health of the service
    r = requests.get(url, timeout=5)
    if r.status_code != requests.codes.ok:
        # there is a problem, send an email
        send_email("Problem with %s" % service, "There has been a problem with %s. You should check the service ASAP." % service, to)

