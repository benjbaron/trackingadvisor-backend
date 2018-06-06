#!/bin/sh

if [[ $# -eq 0 ]] ; then
    echo "Usage:"
    echo "       $0 [api|web|worker] build"
    echo "       $0 [api|web|worker] build run"
    echo "       $0 [api|web|worker] run"
    exit 0
fi

folder=$1

if [ "$2" == "build" ]; then
    echo "Stopping $folder container..."
    docker stop semantica-$folder
    docker rm -f semantica-$folder
    echo "Building a new $folder container..."
    docker build -f $folder/Dockerfile -t semantica-$folder .
    echo "Done building $folder container."
fi

if [ "$2" == "run" ] || [ "$3" == "run" ]; then
    echo "Running $folder container..."

    if [ $folder == "api" ]; then
        docker run -d --restart=always -e DB_HOSTNAME="colossus07" -v ~/semantica/uwsgilogs_$folder:/var/log/uwsgi -v ~/semantica/to_process:/app/to_process -v ~/semantica/magfiles:/app/magfiles --name semantica-$folder -p 8000:8000 -t semantica-$folder
    fi

    if [ $folder == "web" ]; then
        docker run -d --restart=always -e DB_HOSTNAME="colossus07" -v ~/semantica/nginxlogs_$folder:/var/log/nginx --name semantica-$folder -p 8000:8000 -t semantica-$folder
    fi

    if [ $folder == "worker" ]; then
        docker run -d --restart=always -v ~/semantica/cronlogs:/app/cronlogs -v ~/semantica/to_process:/app/to_process -v ~/semantica/user_traces:/app/user_traces --name semantica-$folder -t semantica-$folder
    fi

    echo "Done running $folder"
fi
