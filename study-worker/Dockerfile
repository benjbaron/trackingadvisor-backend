FROM python:3.6

RUN apt-get update && \
    apt-get install -y

# copy over our requirements.txt file
COPY ./study-worker/requirements.txt /tmp/

# upgrade pip and install required python packages
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

COPY ./study-worker/app /app
ADD src /app/
WORKDIR /app

ENTRYPOINT ["python", "/app/worker.py"]