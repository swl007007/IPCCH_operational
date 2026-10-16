#!/bin/sh
# Training entry for Vertex AI (training-ipcch). Vertex HPT mounts /var/hypertune (the CLOUD_ML_HP_METRIC_FILE
# directory) owned root:root 0755 (observed by the O-090 probe), which the runtime user cannot write. Started as root,
# this hands that one directory to 65534:65534 and runs the command as 65534 with no supplementary groups and no
# inheritable capabilities; started as any other user it just runs the command. Nothing else runs as root.
set -eu
if [ "$(id -u)" = 0 ]; then
    if [ -d /var/hypertune ]; then
        chown 65534:65534 /var/hypertune
    fi
    exec setpriv --reuid=65534 --regid=65534 --clear-groups --inh-caps=-all -- "$@"
fi
exec "$@"
