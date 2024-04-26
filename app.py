# A very basic flask app to get the health check working for cgov and terraform. Due to this, the health check is
# currently port based. We should change this in the future, however, for now, this is fine.

from boto3 import client as boto3_client
import environs
import json
import logging
from logging.config import dictConfig
import os
import sys
from flask import Flask
from threading import Thread
from time import sleep

env = environs.Env()

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
        logger.info("loading s3 info")

        vcap = json.loads(env.str("VCAP_SERVICES"))

        s3 = vcap['s3'][0]["credentials"]
        s3_client = boto3_client(
            service_name="s3",
            region_name=s3["region"],
            aws_access_key_id=s3["access_key_id"],
            aws_secret_access_key=s3["secret_access_key"],
            endpoint_url=s3["endpoint"],
            config=Config(signature_version="s3v4"),
        )

        objs = s3_client.list_objects_v2(
            Bucket=s3["bucket"],
            MaxKeys=10,
        )

        logger.info(objs)

        logger.info('this is where I would scan a file')
        sleep(30)


Thread(target=scan_loop, daemon=True).start()

app = Flask(__name__)
port = int(os.getenv('PORT', '8080'))

@app.route('/')
def hello_world():
    return 'Temporary Flask App to ensure Terraform Apply Occurs'

if __name__ == '__main__':
    logger.info("starting up...")
    app.run(host='0.0.0.0', port=port)
