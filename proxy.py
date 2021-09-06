#!/usr/bin/env python3

import requests, logging, os
from flask import Flask
from flask import request

app = Flask(__name__)

logger = logging.getLogger('update-proxy')
logger.setLevel(logging.INFO)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def api_proxy(path):
  channel = request.args.get('channel')
  arch = request.args.get('arch')

  url = "https://api.openshift.com/" + path

  logger.info("forwarding update api call from source {} to upstream {}".format(request.remote_addr, url))

  response = requests.get(url,
    params={'channel': channel, 'arch': arch},
    proxies={
      'https': os.environ.get('HTTPS_PROXY', 'http://localhost:3128'),
    },
  )

  return response.text

if __name__ == '__main__':
  from waitress import serve
  serve(app, host="0.0.0.0", port=5000)
  #app.run(host='0.0.0.0', port=5000)
