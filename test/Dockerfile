FROM python:3.6

RUN apt-get update && \
    apt-get install -y && \
    pip3 install uwsgi

# copy over our requirements.txt file
COPY ./requirements.txt /tmp/

# upgrade pip and install required python packages
RUN pip install -U pip
RUN pip install -r /tmp/requirements.txt

COPY ./uwsgi.ini /app/
COPY ./app /app

WORKDIR /app

EXPOSE 8000

CMD ["uwsgi", "--ini", "/app/uwsgi.ini"]