#!/bin/sh

if [[ $# -eq 0 ]] ; then
    echo "Usage:"
    echo "       $0 {api|web|worker|study|study-worker} build [nb_workers]"
    echo "       $0 {api|web|worker|study|study-worker} build run [nb_workers]"
    echo "       $0 {api|web|worker|study|study-worker|es} run [nb_workers]"
    exit 0
fi

folder=$1
last=${@:$#}
nb_workers=1
if [[ $last =~ ^[0-9]+$ ]] ; then
   nb_workers=$last
fi

if [[ $folder == "es" ]]; then
    echo "Running the Elasticsearch database"
    docker run -d --restart=always -v /home/ucfabb0/mount/es_data:/usr/share/elasticsearch/data -p 9200:9200 -p 9300:9300 -e "discovery.type=single-node" -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" -e http.port=9200 -e http.cors.allow-origin="*" -e http.cors.enabled=true -e http.cors.allow-headers=X-Requested-With,X-Auth-Token,Content-Type,Content-Length,Authorization -e http.cors.allow-credentials=true docker.elastic.co/elasticsearch/elasticsearch:6.5.1
    echo "Done running Elasticsearch database"
    exit 1
fi

if [[ $folder == "strapi" ]]; then
    echo "Running the Strapi CMS"
    docker run -e APP_NAME=strapi-app -e HOST=iss-lab.geog.ucl.ac.uk/semantica/ -e DATABASE_CLIENT=mongo -e DATABASE_HOST=colossus07 -e DATABASE_PORT=27017 -e DATABASE_NAME=strapi -v `pwd`/strapi-app:/usr/src/api/strapi-app -p 8004:1337 --name strapi -d strapi/strapi
    echo "Done running the Strapi CMS"
    exit 1
fi

if [[ $folder == "mysql" ]]; then
    echo "Running the MySQL database"
    docker run -d --restart=always --name mysqldb -v /home/ucfabb0/mount/mysql_data:/var/lib/mysql -e MYSQL_USER=mysql -e MYSQL_PASSWORD=mysql -e MYSQL_DATABASE=sample -e MYSQL_ROOT_PASSWORD=supersecret -p 3306:3306 mysql
    echo "Done running the MySQL database"
    exit 1
fi

if [[ $folder == "wordpress" ]]; then
    echo "Running the Wordpress container"
    docker run --name wordpress-semantica -p 8002:80 -e WORDPRESS_DB_HOST=localhost:3306 -e WORDPRESS_DB_USER=root -e WORDPRESS_DB_PASSWORD=supersecret -e WORDPRESS_DB_NAME=wordpress -e WORDPRESS_CONFIG_EXTRA="define( 'WP_SITEURL', 'https://iss-lab.geog.ucl.ac.uk/semantica/survey/' );  define( 'WP_HOME', 'https://iss-lab.geog.ucl.ac.uk/semantica/survey/' );define('FORCE_SSL_ADMIN', true);\$_SERVER['HTTPS'] = 'on';" -e WORDPRESS_DEBUG=1 -d wordpress-semantica
    echo "Done running the Wordpress container"
    exit 1
fi

if [[ $folder == "mongo" ]]; then
    echo "Running the MongoDB container"
    docker run -d --restart=always -v /home/ucfabb0/mount/db:/data/db --name trackingadvisor-mongo -p 27017:27017 mongo:latest
    echo "Done running the MongoDB container"
    exit 1
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

    if [ $folder == "foursquare-worker" ]; then
        for i in $(seq 1 $nb_workers); do
            docker run -d --restart=always --name semantica-$folder-$i -t semantica-$folder
        done
    fi

    echo "Done running $folder"
fi
