#! /bin/bash

HOST_IP=10.130.35.2
IMAGE_NAME=qingnang_v20260108
IMAGE_VERSION=v1
DOCKER_NAME=seafarer_medical_ai
HOST_WORKSPACE=/data/llm
DOCKER_WORKSPACE=/home/workspace

echo "HOST_IP=${HOST_IP}"
echo "IMAGE_NAME=${IMAGE_NAME}"
echo "IMAGE_VERSION=${IMAGE_VERSION}"
echo "DOCKER_NAME=${DOCKER_NAME}"
echo "HOST_WORKSPACE=${HOST_WORKSPACE}"
echo "DOCKER_WORKSPACE=${DOCKER_WORKSPACE}"

docker_run=`docker ps -a -q --filter "name=^/$DOCKER_NAME$"`
if [  "$docker_run" ]; then
    echo "====================================================="
    echo "ERROR: Container '$DOCKER_NAME' already exists"
    echo "Options:"
    echo "  - Change DOCKER_NAME variable to use a different name"
    echo "  - Remove existing container: docker rm -f $DOCKER_NAME"
    echo "====================================================="
    exit 1
fi

docker run -itd  \
    -v ${HOST_WORKSPACE}:${DOCKER_WORKSPACE} \
    -v /root/.ssh:/root/.ssh \
    --gpus all \
    --pid=host \
    --user=root \
    --cap-add=SYS_PTRACE \
    --privileged=true \
    --ipc=host \
    --network=host \
    --restart=always \
    --ulimit stack=68719476736 \
    --shm-size=100G \
    --name $DOCKER_NAME \
    -w=$DOCKER_WORKSPACE \
    $IMAGE_NAME:$IMAGE_VERSION \
    /bin/bash
