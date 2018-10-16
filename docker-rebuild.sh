#!/bin/sh

if [[ $# -eq 0 ]] ; then
    echo "Usage:"
    echo "       $0 {api|web|worker|study|study-worker} build [nb_workers]"
    echo "       $0 {api|web|worker|study|study-worker} build run [nb_workers]"
    echo "       $0 {api|web|worker|study|study-worker} run [nb_workers]"
    exit 0
fi

folder=$1
last=${@:$#}
nb_workers=1
if [[ $last =~ ^[0-9]+$ ]] ; then
   nb_workers=$last
fi

echo "Stopping $folder container(s)..."
if [[ $folder = *"worker"* ]]; then

    echo "Number of workers: $nb_workers"

    for i in $(seq 1 $nb_workers); do
        echo "stopping semantica-$folder-$i..."
        docker stop semantica-$folder-$i
        docker rm -f semantica-$folder-$i
    done
else
    echo "stopping semantica-$folder..."
    docker stop semantica-$folder
    docker rm -f semantica-$folder
fi

if [ "$2" == "build" ]; then

    if [ $folder == "study-stats" ]; then

        echo "Building a new semantica-$folder container..."
        docker build -f study/DockerfileStats -t semantica-$folder .
        echo "Done building semantica-$folder container."
        
    else

        echo "Building a new semantica-$folder container..."
        docker build -f $folder/Dockerfile -t semantica-$folder .
        echo "Done building semantica-$folder container."

    fi
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
        for i in $(seq 1 $nb_workers); do
            docker run -d --restart=always -v ~/semantica/cronlogs:/app/cronlogs -v ~/semantica/to_process:/app/to_process -v ~/semantica/user_traces:/app/user_traces --name semantica-$folder-$i -t semantica-$folder
        done
    fi

    if [ $folder == "study" ]; then
        docker run -d --restart=always -e DB_HOSTNAME="colossus07" --name semantica-$folder -p 8001:8000 -t semantica-$folder
    fi

    if [ $folder == "study-stats" ]; then
        docker run -d --restart=always -e DB_HOSTNAME="colossus07" --name semantica-$folder -p 8003:8000 -t semantica-$folder
    fi

    if [ $folder == "study-worker" ]; then
        for i in $(seq 1 $nb_workers); do
            docker run -d --restart=always -v ~/word_embeddings:/app/data --name semantica-$folder-$i -t semantica-$folder
        done
    fi

    echo "Done running $folder"
fi
