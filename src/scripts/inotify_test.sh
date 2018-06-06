#!/bin/bash

watchdir=/home/ucfabb0/semantica/to_process
logfile=/home/ucfabb0/semantica/inotify.log
while : ; do
        inotifywait $watchdir|while read path action file; do
                ts=$(date +"%C%y%m%d%H%M%S")
                echo "$ts :: file: $file :: $action :: $path"
                echo "$ts :: file: $file :: $action :: $path" >> $logfile
        done
done
exit 0