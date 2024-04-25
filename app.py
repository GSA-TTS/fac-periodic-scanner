# A very basic flask app to get the health check working for cgov and terraform. Due to this, the health check is
# currently port based. We should change this in the future, however, for now, this is fine.

import logging
from logging.config import dictConfig
import os
import sys
from flask import Flask
from threading import Thread
from time import sleep

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'default': {
        'class': 'logging.StreamHandler',
        'stream': sys.stdout,
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['default']
    }
})

logger = logging.getLogger(__name__)

def scan_loop():
    while True:
        logger.info('this is where I would scan a file')
        sleep(5)


Thread(target=scan_loop, daemon=True).start()

app = Flask(__name__)
port = int(os.getenv('PORT', '8080'))

@app.route('/')
def hello_world():
    return 'Temporary Flask App to ensure Terraform Apply Occurs'

if __name__ == '__main__':
    logger.info("starting up...")
    app.run(host='0.0.0.0', port=port)
