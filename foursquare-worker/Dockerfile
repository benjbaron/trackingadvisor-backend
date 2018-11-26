FROM python:3.6

RUN apt-get update && \
    apt-get install -y

# copy over our requirements.txt file
COPY ./foursquare-worker/requirements.txt /tmp/

# upgrade pip and install required python packages
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

COPY ./foursquare-worker/app /app
ADD src /app/
WORKDIR /app

ENTRYPOINT ["python", "/app/worker.py", "listen"]