from psycopg2 import sql

import utils


def start_session(session_id, ip_address):
    connection, cursor = utils.connect_to_db("study")

    query_string = """INSERT INTO sessions 
    (start, session_id, ip_address)
    VALUES (%s, %s, %s)
    ON CONFLICT DO NOTHING;"""
    data = (utils.current_timestamp(), session_id, ip_address)

    cursor.execute(query_string, data)
    connection.commit()


def add_trackingadvisor_id(session_id, user_id):
    connection, cursor = utils.connect_to_db("study")

    query_string = """UPDATE sessions SET user_id = %s WHERE session_id = %s;"""
    data = (user_id, session_id)

    cursor.execute(query_string, data)
    connection.commit()


def end_session(session_id):
    connection, cursor = utils.connect_to_db("study")

    query_string = """UPDATE sessions SET end = %s WHERE session_id = %s;"""
    data = (utils.current_timestamp(), session_id)

    cursor.execute(query_string, data)
    connection.commit()


def save_place(session_id, place_id, place_name):
    connection, cursor = utils.connect_to_db("study")

    query_string = """INSERT INTO places 
    (place_id, session_id, place_name)
    VALUES (%s, %s, %s)
    ON CONFLICT DO NOTHING;"""
    data = (place_id, session_id, place_name)

    cursor.execute(query_string, data)
    connection.commit()


def save_personal_information_relevance(session_id, place_id, pi_id, rating):
    connection, cursor = utils.connect_to_db("study")

    query_string = """INSERT INTO place_personal_information_relevance 
        (pi_id, place_id, session_id, rating)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (session_id, place_id, pi_id) DO UPDATE SET rating=EXCLUDED.rating;"""
    data = (pi_id, place_id, session_id, rating)

    cursor.execute(query_string, data)
    connection.commit()


def save_personal_information_privacy(session_id, pi_id, rating):
    connection, cursor = utils.connect_to_db("study")

    query_string = """INSERT INTO place_personal_information_privacy
        (pi_id, session_id, rating)
        VALUES (%s, %s, %s)
        ON CONFLICT (session_id, pi_id) DO UPDATE SET rating=EXCLUDED.rating;"""
    data = (pi_id, session_id, rating)

    cursor.execute(query_string, data)
    connection.commit()


def save_place_question(session_id, place_id, t, rating):
    connection, cursor = utils.connect_to_db("study")

    col = 'know_rating' if t == 'q1' else 'private_rating'

    query_string = sql.SQL("UPDATE places SET {} = %s WHERE session_id = %s AND place_id = %s;").format(sql.Identifier(col))
    data = (rating, session_id, place_id)

    cursor.execute(query_string, data)
    connection.commit()
