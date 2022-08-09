#!/usr/bin/env python3

import requests, logging, os
from flask import Flask
from flask import request

app = Flask(__name__)

logger = logging.getLogger('update-proxy')
logger.setLevel(logging.INFO)

if not os.environ.get('IGNORE_SSL', False):
  ssl_verify = False
else:
  ssl_verify = True

@app.route('/', defaults={'path': ''})
@app.route('/api/<path:path>')
def api_proxy(path):
  channel = request.args.get('channel')
  arch = request.args.get('arch')

  url = "https://api.openshift.com/api/" + path

  logger.info("forwarding update api call from source {} to upstream {}".format(request.remote_addr, url))

  response = requests.get(url,
    params={'channel': channel, 'arch': arch},
    proxies={
      'https': os.environ.get('HTTPS_PROXY', 'http://localhost:3128'),
    },
    verify = ssl_verify,
  )

  return response.text

@app.route('/pub/<path:path>')
def mirror_proxy(path):
  url = "https://mirror.openshift.com/pub/" + path

  logger.info("forwarding update api call from source {} to upstream {}".format(request.remote_addr, url))

  response = requests.get(url,
    proxies={
      'https': os.environ.get('HTTPS_PROXY', 'http://localhost:3128'),
    },
    verify = ssl_verify,
  )

  return response.text

if __name__ == '__main__':
  from waitress import serve
  serve(app, host="0.0.0.0", port=5000)
  #app.run(host='0.0.0.0', port=5000)
