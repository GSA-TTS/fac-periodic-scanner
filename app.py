# A very basic flask app to get the health check working for cgov and terraform. Due to this, the health check is
# currently port based. We should change this in the future, however, for now, this is fine.

from boto3 import client as boto3_client
from botocore.client import ClientError, Config
from datetime import datetime
from enum import Enum
import environs
from io import BytesIO
import json
import logging
from logging.config import dictConfig
import os
import sys
from flask import Flask
from threading import Thread
from time import sleep
import requests

from config import S3Config, EnvS3Config, ClamAVConfig, EnvClamAVConfig

from peewee import *

env = environs.Env()

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
            }
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["default"]},
    }
)

FILE_REFRESH_INTERVAL_SECS = 600
FILE_SCAN_INTERVAL_SECS = 1

db = SqliteDatabase("scanner.db")


class ScannedFile(Model):
    filename = CharField(unique=True)
    last_scan_timestamp = DateTimeField(null=True)
    last_scan_result = CharField()

    class Meta:
        database = db


logger = logging.getLogger(__name__)


class ScanResult(Enum):
    CLEAN = (1,)
    INFECTED = (2,)
    UNKNOWN = 3

    @classmethod
    def from_http_status(cls, http_status: int):
        if http_status == 200:
            return ScanResult.CLEAN
        elif http_status == 406:
            return ScanResult.INFECTED
        else:
            return ScanResult.UNKNOWN


def construct_s3_client(config: S3Config) -> boto3_client:
    s3_client = boto3_client(
        service_name="s3",
        region_name=config.region_name,
        aws_access_key_id=config.aws_access_key_id,
        aws_secret_access_key=config.aws_secret_access_key,
        endpoint_url=config.aws_endpoint_url,
        config=Config(signature_version="s3v4"),
    )

    return s3_client


def scan_file(clamav_config: ClamAVConfig, file) -> ScanResult:
    response = requests.post(
        clamav_config.endpoint_url,
        files={"file": file},
        timeout=30,
    )

    return ScanResult.from_http_status(response.status_code)


def prepare_env():
    # read .env file if there is one
    res = env.read_env(recurse=False, override=True)

    # load VCAP_SERVICES into env if defined
    try:
        vcap_services = json.loads(env.str("VCAP_SERVICES"))

        # S3 configuration
        s3_credentials = vcap_services["s3"][0]["credentials"]
        os.environ["AWS_S3_REGION_NAME"] = s3_credentials["region"]
        os.environ["AWS_S3_ACCESS_KEY_ID"] = s3_credentials["access_key_id"]
        os.environ["AWS_S3_SECRET_ACCESS_KEY"] = s3_credentials["secret_access_key"]
        os.environ["AWS_S3_ENDPOINT_URL"] = f"https://{s3_credentials['endpoint']}"
        os.environ["AWS_S3_BUCKET"] = s3_credentials["bucket"]

        # ClamAV configuration
        for ups in vcap_services["user-provided"]:
            if ups["name"] == "clamav_ups":
                clamav_credentials = ups["credentials"]
                os.environ["CLAMAV_ENDPOINT_URL"] = clamav_credentials["AV_SCAN_URL"]

    except:
        logger.info("no VCAP_SERVICES defined in env")


def create_scanned_file(filename, scan_timestamp, scan_result):
    ScannedFile.insert(
        filename=filename,
        last_scan_timestamp=scan_timestamp,
        last_scan_result=scan_result,
    ).on_conflict_ignore().execute()


def upsert_scanned_file(filename, scan_timestamp, scan_result):
    ScannedFile.insert(
        filename=filename,
        last_scan_timestamp=scan_timestamp,
        last_scan_result=scan_result,
    ).on_conflict(
        conflict_target=[ScannedFile.filename],
        preserve=[ScannedFile.last_scan_timestamp, ScannedFile.last_scan_result],
    ).execute()


def refresh_files():
    """
    Periodically scan the target S3 bucket and created a ScannedFile entry in the database for file
    """
    s3_config = EnvS3Config(env)
    s3_client = construct_s3_client(s3_config)

    while True:
        logger.info("refreshing files...")

        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=s3_config.bucket)

        if pages:
            for page in pages:
                if "Contents" in page:
                    for object_summary in page["Contents"]:
                        object_name = object_summary["Key"]
                        scan_timestamp = None
                        scan_result = ScanResult.UNKNOWN

                        create_scanned_file(object_name, scan_timestamp, scan_result)

        logger.info("done refreshing files...")

        sleep(FILE_REFRESH_INTERVAL_SECS)


def scan_files():
    """
    Fetch the least recently scanned file from the database, scan it, and update its database record with the new scan result & timestamp
    """
    while True:
        s3_config = EnvS3Config(env)

        s3_client = construct_s3_client(s3_config)

        clamav_config = EnvClamAVConfig(env)

        # scan the least recently scanned file in the database
        for scanned_file in (
            ScannedFile.select().order_by(ScannedFile.last_scan_timestamp).limit(1)
        ):
            file = BytesIO()
            s3_client.download_fileobj(s3_config.bucket, scanned_file.filename, file)
            file.seek(0)

            scan_result = scan_file(clamav_config, file)

            upsert_scanned_file(scanned_file.filename, datetime.utcnow(), scan_result)

            logger.info(f"{scanned_file.filename}: scan result: {scan_result}")

            sleep(FILE_SCAN_INTERVAL_SECS)


app = Flask(__name__)


@app.route("/")
def health_check():
    logger.info("handling health check")
    return "healthy"


def create_app():
    prepare_env()

    db.connect()
    db.create_tables([ScannedFile])

    file_refresh_worker = Thread(target=refresh_files, daemon=True)
    file_refresh_worker.start()

    scan_worker = Thread(target=scan_files, daemon=True)
    scan_worker.start()

    return app


if __name__ == "__main__":
    logger.info("starting up...")

    port = int(os.getenv("PORT", "8080"))
    create_app().run(host="0.0.0.0", port=port)
