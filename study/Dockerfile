FROM python:3.6

RUN apt-get update && \
    apt-get install -y && \
    pip3 install eventlet

# copy over our requirements.txt file
COPY ./study/requirements.txt /tmp/

# upgrade pip and install required python packages
RUN pip install -U pip
RUN pip install -r /tmp/requirements.txt

COPY ./study/uwsgi.ini /app/
COPY ./study/app /app
ADD src /app/

WORKDIR /app

EXPOSE 8000

CMD python3.6 main.py