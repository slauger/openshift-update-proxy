FROM docker.io/python:3.11.4@sha256:9a1b705aecedc76e8bf87dfca091d7093df3f2dd4765af6c250134ce4298a584

RUN pip3 install requests flask waitress

COPY proxy.py /proxy.py

EXPOSE 5000

CMD ["/proxy.py"]
