FROM openjdk:11.0.11-jdk-slim
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*
RUN pip3 install numpy scipy matplotlib javalang
WORKDIR /EMOTE-artifact
COPY . /EMOTE-artifact
