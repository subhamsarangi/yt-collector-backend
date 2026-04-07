import os
import boto3
from botocore.config import Config


def get_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


BUCKET = lambda: os.environ["R2_BUCKET_NAME"]
PUBLIC_URL = lambda: os.environ["R2_PUBLIC_URL"].rstrip("/")


def upload(key: str, data: bytes, content_type: str) -> str:
    get_client().put_object(
        Bucket=BUCKET(), Key=key, Body=data, ContentType=content_type
    )
    return f"{PUBLIC_URL()}/{key}"


def delete(key: str):
    get_client().delete_object(Bucket=BUCKET(), Key=key)
