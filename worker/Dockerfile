FROM python:3.6

RUN apt-get -y update && apt-get -y install python2.7 python-pip

# copy over our requirements.txt file
COPY ./worker/requirements.txt /tmp/
#COPY ./worker/supervisord.conf /etc/supervisord.conf

# upgrade pip and install required python packages
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt
#RUN pip2 install supervisor

COPY ./worker/app /app
ADD src /app/
WORKDIR /app

#ENTRYPOINT ["supervisord", "--configuration", "/etc/supervisord.conf"]
ENTRYPOINT ["python", "/app/worker.py"]