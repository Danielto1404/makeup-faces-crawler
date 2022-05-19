FROM ubuntu:focal
ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN apt-get update -y && apt-get upgrade -y
RUN apt-get install python3 python3-pip libopencv-dev python3-opencv nano vim -y

WORKDIR /app

RUN pip3 install cmake

COPY requirements.txt /app/requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

ENTRYPOINT /bin/bash
