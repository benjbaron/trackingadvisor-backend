#!/bin/sh

if [[ $# -eq 0 ]] ; then
    echo "Usage:"
    echo "       $0 build"
    echo "       $0 build run"
    echo "       $0 run"
    exit 0
fi

if [ "$1" == "build" ]; then
    echo "Stopping container..."
    docker stop semantica
    docker rm semantica
    echo "Building a new container..."
    docker build -t semantica .
    echo "Done building container."
fi

if [ "$1" == "run" ] || [ "$2" == "run" ]; then
    echo "Running container..."
    docker run -d --restart=always -e DB_HOSTNAME="colossus07" -v ~/semantica/nginxlogs:/var/log/nginx -v ~/semantica/to_process:/app/to_process --name semantica -p 80:80 -t semantica
    echo "Done"
fi