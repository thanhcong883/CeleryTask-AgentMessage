import boto3
from botocore.exceptions import ClientError
import config
import os
import time
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


def get_folder_structure(platform_name: str, conversation_id: str) -> str:
    """
    Generate folder structure: YYYY/MM/DD/platform/conversation_id/HH
    """
    now = datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    hour = now.strftime("%H")

    return f"{year}/{month}/{day}/{platform_name}/{conversation_id}/{hour}"


def download_file_generic(url: str, save_path: str) -> bool:
    """
    Generic file download via GET.
    """
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        # Ensure directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        logger.error(f"Failed to download file from {url}: {e}")
        return False


def download_telegram_file(file_id: str, token: str, save_path: str) -> bool:
    """
    Download file from Telegram.
    """
    try:
        # Get file path
        url_get_file = f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
        resp = requests.get(url_get_file, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            logger.error(f"Telegram getFile failed: {data}")
            return False

        file_path = data["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"

        return download_file_generic(download_url, save_path)
    except Exception as e:
        logger.error(f"Failed to download telegram file {file_id}: {e}")
        return False


def upload_to_s3(local_path: str, s3_key: str) -> Optional[str]:
    """
    Upload a file to an S3 bucket

    :param local_path: File to upload
    :param s3_key: S3 object name (e.g. year/month/day/platform/conv_id/filename.ext)
    :return: S3 public URL if successful, else None
    """
    if (
        not config.AWS_ACCESS_KEY_ID
        or not config.AWS_SECRET_ACCESS_KEY
        or not config.AWS_BUCKET_NAME
    ):
        logger.error("AWS credentials or bucket name not configured.")
        return None

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=config.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
        region_name=config.AWS_REGION,
    )

    try:
        s3_client.upload_file(local_path, config.AWS_BUCKET_NAME, s3_key)

        # Determine the URL format based on region (standard AWS format)
        if config.AWS_REGION == "us-east-1":
            url = f"https://{config.AWS_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
        else:
            url = f"https://{config.AWS_BUCKET_NAME}.s3.{config.AWS_REGION}.amazonaws.com/{s3_key}"

        logger.info(f"Successfully uploaded {local_path} to {url}")

        # Cleanup local file after successful upload
        try:
            os.remove(local_path)
        except Exception as e:
            logger.warning(f"Failed to remove local file {local_path}: {e}")

        return url
    except ClientError as e:
        logger.error(f"Failed to upload {local_path} to S3: {e}")
        return None
