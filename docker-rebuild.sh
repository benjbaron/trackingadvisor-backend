#!/bin/sh

if [ "$1" == "build" ]; then
    docker stop semantica
    docker rm semantica
    docker build -t semantica .
fi

if [ "$1" == "run" ] || [ "$2" == "run" ]; then
    docker run -d --restart=always -v ~/semantica/nginxlogs:/var/log/nginx -v ~/semantica/to_process:/app/to_process --name semantica -p 80:80 -t semantica
fi