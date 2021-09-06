FROM docker.io/python

RUN pip3 install requests flask waitress

COPY proxy.py /proxy.py

EXPOSE 5000

CMD ["/proxy.py"]
