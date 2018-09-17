import sys
from apns import APNs, Frame, Payload
from raven import Client

import user_traces_db
import utils

client = Client('https://8f77b4f7e5a6410194f5826deaa3f9f4:74d1d77376ea4f7f8785cb192e62daeb@sentry.io/1207941')


def send_enhanced_push_notification(user_id, message):
    import random

    def response_listener(error_response):
        print("client get error-response: " + str(error_response))

    user = user_traces_db.load_user_info(user_id)
    token_hex = user['push_notification_id']
    apns_enhanced = APNs(use_sandbox=False, cert_file='apns_trackingadvisor.pem', enhanced=True)
    payload = Payload(alert=message, sound="default", badge=1)
    identifier = random.getrandbits(32)
    apns_enhanced.gateway_server.send_notification(token_hex, payload, identifier=identifier)

    apns_enhanced.gateway_server.register_response_listener(response_listener)


def send_push_notification_review_challenge(user_id, day, message):
    user = user_traces_db.load_user_info(user_id)
    review_challenge = user_traces_db.load_user_review_challenge(user_id, day)

    review_challenge_days = list(set([rc['day'] for rc in review_challenge]))
    print(review_challenge_days)

    apns = APNs(use_sandbox=True, cert_file='apns-cert.pem', key_file='apns-key-noenc.pem')
    token_hex = user['push_notification_id']
    payload = Payload(alert=message, sound="default", badge=1, category="REVIEW_CHALLENGE",
                      custom={'challenges': review_challenge_days})
    apns.gateway_server.send_notification(token_hex, payload)

    print("Done")


def send_push_notification_update(user_id):
    user = user_traces_db.load_user_info(user_id)

    apns = APNs(use_sandbox=True, cert_file='apns_trackingadvisor.pem')
    token_hex = user['push_notification_id']
    payload = Payload(content_available=True)
    apns.gateway_server.send_notification(token_hex, payload)

    print("Done")


def send_push_notification_test(user_id, message):
    user = user_traces_db.load_user_info(user_id)

    apns = APNs(use_sandbox=False, cert_file='apns_trackingadvisor.pem')
    token_hex = user['push_notification_id']

    print(token_hex)

    payload = Payload(alert=message, sound="default", badge=1)
    apns.gateway_server.send_notification(token_hex, payload)

    for (token_hex, fail_time) in apns.feedback_server.items():
        print(token_hex, fail_time)

    print("Done")


def send_push_notification(user_id, type, message, args='', use_sandbox=False):
    user = user_traces_db.load_user_info(user_id)
    apns = APNs(use_sandbox=use_sandbox, cert_file='apns_trackingadvisor.pem')
    token_hex = user['push_notification_id']

    d = {'type': type}
    if type == "review":
        d['title'] = "You have personal information to review"
        d['message'] = "Do you want to review personal information about the places you visited?"
        payload = Payload(alert=message, sound="default", badge=1, custom=d)
    elif type == "timeline" and args != "":
        d['day'] = args
        d['title'] = "You have visits to review"
        d['message'] = "Do you want to review your visits yesterday?"
        payload = Payload(alert=message, sound="default", badge=1, custom=d)
    elif type == "web" and args != "":
        d['url'] = args
        d['title'] = "Show the final study survey"
        d['message'] = "Do you want to display the final study survey? This will help us get useful feedback from you."
        payload = Payload(alert=message, sound="default", badge=1, custom=d)
    elif type == "message" and args:
        d['title'] = "New message"
        d['message'] = "Do you want to read your new message?"
        d['msg'] = args['message']
        d['timestamp'] = args['timestamp']
        payload = Payload(alert={'title': "New message", 'body': args['message']}, sound="default", badge=1, custom=d)

    if payload is not None:
        apns.gateway_server.send_notification(token_hex, payload)


def send_survey_notification_to_user(user_id, url, use_sandbox=False):
    user = user_traces_db.load_user_info(user_id)
    apns = APNs(use_sandbox=use_sandbox, cert_file='apns_trackingadvisor.pem')
    token_hex = user['push_notification_id']

    title = "Hey there 👋"
    body = "Thank you for participating in the study! We have a survey for you to fill ... Tap to open it!"

    alert = {
        "title": title,
        "body": body
    }

    d = {
        "type": "web",
        "url": url+"?user_id=%s" % user_id,
        "title": title,
        "message": body
    }

    payload = Payload(alert=alert, sound="default", badge=1, custom=d)
    apns.gateway_server.send_notification(token_hex, payload)


def send_survey_notification_to_all_users(url):
    import os
    import math
    import datetime
    import calendar
    import logging

    os.chdir("/home/ucfabb0/code/semantica-docker/src/")
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)

    users = user_traces_db.get_all_users_push_ids()
    count_users = 0

    try:
        utc_dt = datetime.datetime.utcnow()
        utc_time = calendar.timegm(utc_dt.utctimetuple())

        for user in users:
            user_id = user['user_id']

            # get the last update
            last_user_update = user_traces_db.get_last_user_update(user_id)
            if not last_user_update:
                logging.warning("[%s] no traces available for user" % user_id)
                continue

            # get the user join date
            user_join_date = user_traces_db.get_user_join_date(user_id)
            if not user_join_date:
                logging.warning("[%s] no join date available" % user_id)

            last_update_within_48_hours = math.fabs(last_user_update - utc_time) <= 2 * 24 * 3600
            has_join_for_more_than_one_week = math.fabs(user_join_date - utc_time) > 7 * 24 * 3600

            if not last_update_within_48_hours:
                logging.warning("[%s] not updated since 48 hours" % user_id)
                continue

            if not has_join_for_more_than_one_week:
                logging.warning("[%s] not joined since one week" % user_id)
                continue

            count_users += 1
            logging.info("[%s] Send notification - survey" % user_id)
            send_survey_notification_to_user(user_id, url, use_sandbox=True)
            send_survey_notification_to_user(user_id, url, use_sandbox=False)

    except:
        client.captureException()

    logging.info("[Done] processed %s users out of %s total users" % (count_users, len(users)))


def schedule_notifications():
    import os
    import math
    import datetime
    import calendar
    import logging

    os.chdir("/home/ucfabb0/code/semantica-docker/src/")

    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO)

    def is_visit_confirmed(visit):
        return visit['visited'] is not None or visit['deleted']

    def is_aggregated_personal_information_reviewed(pi):
        return pi['rpi'] > 0 and pi['rpriv'] > 0

    def is_personal_information_reviewed(pi):
        return pi['r'] > 0

    try:
        users = user_traces_db.get_all_users_push_ids()

        utc_dt = datetime.datetime.utcnow()
        utc_time = calendar.timegm(utc_dt.utctimetuple())

        number_of_days = 2
        days = set()
        day = utils.today_string()
        today = day
        for i in range(number_of_days):
            days.add(day)
            day = utils.previous_day(day)

        count_users = 0
        # user_filter = {'cab40ba2-244b-4394-aca1-4b1d87d969df', 'f5eb6ac8-adbc-4d1c-acf3-627d6fa95664',
        #                '4b2c57ae-5060-464d-9a9a-38a92268910f', '02cd63b6-a58d-4209-a9b4-b733a7fff2ae'}
        for user in users:
            user_id = user['user_id']

            # if user_id not in user_filter:
            #     continue

            has_visits_to_confirm = False
            has_places_to_review = False
            has_personal_information_to_review = False
            last_update_within_48_hours = False
            has_join_for_more_than_24_hours = False

            # get the last update
            last_user_update = user_traces_db.get_last_user_update(user_id)
            if not last_user_update:
                logging.warning("[%s] no traces available for user" % user_id)
                continue

            # get the user join date
            user_join_date = user_traces_db.get_user_join_date(user_id)
            if not user_join_date:
                logging.warning("[%s] no join date available" % user_id)

            last_update_within_48_hours = math.fabs(last_user_update-utc_time) <= 96*3600
            has_join_for_more_than_24_hours = math.fabs(user_join_date-utc_time) > 24*3600

            if not last_update_within_48_hours:
                logging.warning("[%s] not updated since 48 hours" % user_id)
                continue

            if not has_join_for_more_than_24_hours:
                logging.warning("[%s] not joined since 24 hours" % user_id)
                continue

            # get the latest utc offset
            utc_offset = user_traces_db.get_last_user_utc_offset(user_id)
            local_time = utc_time - utc_offset
            logging.info("[%s] utc offset: %s, local time: %s" % (user_id, utc_offset, utils.day_hm(local_time)))

            local_dt = utils.datetime_from_timestamp(local_time)
            hour = local_dt.hour

            if hour != 20:
                logging.warning("[%s] not 20:00 local time yet (%s, %s)" % (user_id, utils.day_hm(local_time), hour))
                continue

            # visits
            visits = user_traces_db.load_user_all_visits(user_id)
            if len(visits) > 0:
                # if this is around the time to send a notification,
                # check if we can send a notification
                recent_visits_to_confirm = [v['visit_id'] for v in visits if
                                            not is_visit_confirmed(v) and v['day'] in days]
                total_number_of_recent_visits_to_confirm = len(recent_visits_to_confirm)

                if total_number_of_recent_visits_to_confirm > 0:
                    has_visits_to_confirm = True

            # personal information per places
            personal_information = user_traces_db.load_all_user_personal_information(user_id)
            if len(personal_information) > 0:
                personal_information_per_place = {}
                for pi in personal_information:
                    pid = pi['pid']
                    if pid not in personal_information_per_place:
                        personal_information_per_place[pid] = []
                    personal_information_per_place[pid].append(pi)

                total_number_of_personal_information = 0
                total_number_of_personal_information_to_review = 0
                total_number_of_personal_information_reviewed = 0
                for pid, pis in personal_information_per_place.items():
                    number_of_personal_information = len(pis)
                    personal_information_to_review = [pi['piid'] for pi in pis if not is_personal_information_reviewed(pi)]
                    personal_information_reviewed = [pi['piid'] for pi in pis if is_personal_information_reviewed(pi)]
                    total_number_of_personal_information += number_of_personal_information
                    total_number_of_personal_information_to_review += 1 if len(personal_information_to_review) > 0 else 0
                    total_number_of_personal_information_reviewed += 1 if len(personal_information_reviewed) > 0 else 0

                if total_number_of_personal_information_to_review > 0:
                    has_places_to_review = True

            # aggregated personal information
            aggregated_personal_information = user_traces_db.load_user_aggregated_personal_information(user_id)
            if len(aggregated_personal_information) > 0:
                aggregated_personal_information_to_review = [pi['piid'] for pi in aggregated_personal_information if not is_aggregated_personal_information_reviewed(pi)]
                number_of_aggregated_personal_information_to_review = len(aggregated_personal_information_to_review)
                if number_of_aggregated_personal_information_to_review > 0:
                    has_personal_information_to_review = True

            count_users += 1

            # prepare the message to send via push notification
            logging.info("[%s] visits %s / places %s / personal information %s" % (user_id, has_visits_to_confirm, has_places_to_review, has_personal_information_to_review))
            if has_visits_to_confirm:
                logging.info("[%s] Send notification - visits" % user_id)
                message = "✅ We have detected new visits! Tap to review them"
                type = "timeline"
                send_push_notification(user_id, type, message, today, use_sandbox=True)
                send_push_notification(user_id, type, message, today, use_sandbox=False)

            elif has_places_to_review or has_personal_information_to_review:
                logging.info("[%s] Send notification - reviews" % user_id)
                message = "✅ We have detected new personal information about you! Tap to review them"
                type = "review"
                send_push_notification(user_id, type, message, use_sandbox=True)
                send_push_notification(user_id, type, message, use_sandbox=False)
    except:
        client.captureException()

    logging.info("[Done] processed %s users out of %s total users" % (count_users, len(users)))


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print("Error - you should choose an argument:")
        base = sys.argv[0]
        print('\t{} push user_id day message'.format(base))
        print('\t{} push-update user_id'.format(base))
        print('\t{} push-test user_id message'.format(base))
        sys.exit(0)

    arg = sys.argv[1]
    if arg == 'push':
        if len(sys.argv) != 5:
            print("Error - you should provide a valid user id, a day (yyyy-mm-dd), and a message (in quotes)")
            sys.exit(0)

        user_id = sys.argv[2]
        day = sys.argv[3]
        message = sys.argv[4]

        send_push_notification_review_challenge(user_id, day, message)

    elif arg == 'push-type':
        if len(sys.argv) < 5:
            print("Error - you should provide a valid user id, a type (timeline|review), a message (in quotes), and a day (optional)")
            sys.exit(0)

        user_id = sys.argv[2]
        notification_type = sys.argv[3]
        message = sys.argv[4]
        day = sys.argv[5] if len(sys.argv) > 5 else ""

        send_push_notification(user_id, notification_type, message, day, use_sandbox=True)

    elif arg == 'push-update':
        if len(sys.argv) != 3:
            print("Error - you should provide a valid user id")
            sys.exit(0)

        user_id = sys.argv[2]
        send_push_notification_update(user_id)

    elif arg == 'push-test':
        if len(sys.argv) != 4:
            print("Error - you should provide a valid user id, and a message (in quotes)")
            sys.exit(0)

        user_id = sys.argv[2]
        message = sys.argv[3]
        send_enhanced_push_notification(user_id, message)

    elif arg == 'schedule':
        schedule_notifications()

    elif arg == 'push-survey':
        if len(sys.argv) != 3:
            print("Error - you should provide a valid survey url (in quotes)")
            sys.exit(0)

        url = sys.argv[2]
        send_survey_notification_to_all_users(url)

    elif arg == 'push-survey-user':
        if len(sys.argv) != 4:
            print("Error - you should provide a valid survey url and user id (both in quotes)")
            sys.exit(0)

        url = sys.argv[2]
        user_id = sys.argv[3]
        send_survey_notification_to_user(user_id, url, use_sandbox=False)
        send_survey_notification_to_user(user_id, url, use_sandbox=True)

    else:
        print("Error - specify an argument search")
        sys.exit(0)
