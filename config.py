import environs

class S3Config:
    def __init__(self):
        self.region_name = ""
        self.aws_access_key_id = ""
        self.aws_secret_access_key = ""
        self.aws_endpoint_url = ""
        self.bucket = ""


class EnvS3Config(S3Config):
    def __init__(self, env: environs.Env):
        self.region_name = env.str("AWS_S3_REGION_NAME")
        self.aws_access_key_id = env.str("AWS_S3_ACCESS_KEY_ID")
        self.aws_secret_access_key = env.str("AWS_S3_SECRET_ACCESS_KEY")
        self.aws_endpoint_url = env.str("AWS_S3_ENDPOINT_URL")
        self.bucket = env.str("AWS_S3_BUCKET")


class ClamAVConfig:
    def __init__(self):
        self.endpoint_url = ""


class EnvClamAVConfig(ClamAVConfig):
    def __init__(self, env: environs.Env):
        self.endpoint_url = env.str("CLAMAV_ENDPOINT_URL")
