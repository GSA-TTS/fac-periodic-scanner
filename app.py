# A very basic flask app to get the health check working for cgov and terraform
# Due to this, the health check is currently port based. 
# We should change this in the future, however, for now, this is fine.

from boto3 import client as boto3_client
from botocore.client import ClientError, Config
from datetime import datetime, timedelta
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

SCAN_LOOP_INTERVAL_SECS = 60
FILE_SCAN_INTERVAL_DAYS = 60
DEFAULT_LAST_SCAN_TIMESTAMP = datetime.utcfromtimestamp(0).isoformat()

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
        timeout=180,
    )

    return ScanResult.from_http_status(response.status_code)


def prepare_env():
    # read .env file if there is one
    env.read_env(recurse=False, override=True)

    # load VCAP_SERVICES into env if defined
    try:
        vcap_services = json.loads(env.str("VCAP_SERVICES"))

        # S3 configuration
        fac_private_s3 = next(x for x in vcap_services["s3"] if x["name"] == "fac-private-s3")

        s3_credentials = fac_private_s3["credentials"]
        os.environ["AWS_S3_REGION_NAME"] = s3_credentials["region"]
        os.environ["AWS_S3_ACCESS_KEY_ID"] = s3_credentials["access_key_id"]
        os.environ["AWS_S3_SECRET_ACCESS_KEY"] = s3_credentials[
            "secret_access_key"
        ]
        os.environ["AWS_S3_ENDPOINT_URL"] = (
            f"https://{s3_credentials['endpoint']}"
        )
        os.environ["AWS_S3_BUCKET"] = s3_credentials["bucket"]

        # ClamAV configuration
        for ups in vcap_services["user-provided"]:
            if ups["name"] == "clamav_ups":
                clamav_credentials = ups["credentials"]
                os.environ["CLAMAV_ENDPOINT_URL"] = clamav_credentials[
                    "AV_SCAN_URL"
                ]

    except:
        logger.info("no VCAP_SERVICES defined in env")


def object_needs_scan(s3_config: S3Config, object_name: str) -> bool:
    s3_client = construct_s3_client(s3_config)

    try:
        tagging = s3_client.get_object_tagging(
            Bucket=s3_config.bucket, Key=object_name
        )

        tags = tagging["TagSet"]
        last_scan_timestamp = datetime.fromisoformat(next(
            (t["Value"] for t in tags if t["Key"] == "last_scan_timestamp"),
            DEFAULT_LAST_SCAN_TIMESTAMP,
        ))

        time_since_last_scan = datetime.utcnow() - last_scan_timestamp

        return time_since_last_scan > timedelta(days=FILE_SCAN_INTERVAL_DAYS)
    except ClientError as e:
        logger.warn(f"error while getting tags for {object_name}: {e}")
        return False


def update_object_scan_timestamp(s3_config: S3Config, object_name: str):
    s3_client = construct_s3_client(s3_config)

    try:
        s3_client.put_object_tagging(
            Bucket=s3_config.bucket,
            Key=object_name,
            Tagging={
                "TagSet": [
                    {
                        "Key": "last_scan_timestamp",
                        "Value": datetime.utcnow().isoformat(),
                    }
                ]
            },
        )
    except ClientError as e:
        logger.warn(f"error while putting tags for {object_name}: {e}")


def download_file(s3_config: S3Config, object_name: str) -> BytesIO:
    s3_client = construct_s3_client(s3_config)

    try:
        file = BytesIO()
        s3_client.download_fileobj(s3_config.bucket, object_name, file)
        file.seek(0)

        return file
    except ClientError as e:
        logger.warn(f"error while downloading {object_name}: {e}")
        return None


def scan_files():
    """
    Fetch the least recently scanned file from the database, scan it, and update its database record with the new scan result & timestamp
    """

    s3_config = EnvS3Config(env)
    s3_client = construct_s3_client(s3_config)

    clamav_config = EnvClamAVConfig(env)

    while True:
        object_count = 0
        
        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=s3_config.bucket, Prefix="singleauditreport")

            if pages:
                page_index = 0
                for page in pages:
                    page_index += 1
                    if "Contents" in page:
                        for object_summary in page["Contents"]:
                            try:
                                object_count += 1
                                object_name = object_summary["Key"]

                                if object_needs_scan(s3_config, object_name):
                                    file = download_file(s3_config, object_name)

                                    if file:
                                        scan_result = scan_file(clamav_config, file)
                                        update_object_scan_timestamp(s3_config, object_name)

                                        logger.info(
                                            f"{object_name} scan result: {scan_result}"
                                        )
                            except Exception as e:
                                logger.warn(f"error while scanning {object_name}: {e}")

                    logger.info(f"finished checking page {page_index} ({page['KeyCount']} objects)")
        except Exception as e:
            logger.warn(f"error while scanning: {e}")
        finally:
            logger.info(f"checked {object_count} files, waiting {SCAN_LOOP_INTERVAL_SECS}s before restarting")
            sleep(SCAN_LOOP_INTERVAL_SECS)


app = Flask(__name__)


@app.route("/")
def health_check():
    logger.info("handling health check")
    return "healthy"


def create_app():
    prepare_env()

    scan_worker = Thread(target=scan_files, daemon=True)
    scan_worker.start()

    return app


if __name__ == "__main__":
    logger.info("starting up...")

    port = int(os.getenv("PORT", "8080"))
    create_app().run(host="0.0.0.0", port=port)
