import boto3
from botocore.exceptions import ClientError
import config
import os
import re
import time
import uuid
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    """Sanitize a filename for safe use in S3 keys and URLs.

    Keeps ASCII alphanumerics, dot, dash, underscore. Everything else
    (spaces, brackets, unicode, etc.) is collapsed to a single underscore.
    """
    if not name:
        return ""
    cleaned = _SAFE_FILENAME_RE.sub("_", name)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_.")
    return cleaned


def build_media_filename(
    message_type: str, original_name: Optional[str], ext: str
) -> str:
    """Build the final stored filename for a media upload.

    - `file` with a known original name: ``<uuid>_<sanitized_original>``.
    - Everything else: ``<uuid>.<ext>``.
    """
    uid = uuid.uuid4().hex
    if message_type == "file" and original_name:
        safe = safe_filename(original_name)
        if safe:
            if "." not in safe:
                safe = f"{safe}.{ext}"
            return f"{uid}_{safe}"
    return f"{uid}.{ext}"


def get_folder_structure(platform_name: str, conversation_id: str) -> str:
    """
    Generate folder structure: YYYY/MM/DD/platform/conversation_id
    """
    now = datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")

    return f"{year}/{month}/{day}/{platform_name}/{conversation_id}"


def download_file_generic(url: str, save_path: str) -> bool:
    """
    Generic file download via GET.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, stream=True, timeout=30, headers=headers)
        logger.info(
            f"Download response: status={response.status_code}, "
            f"content-length={response.headers.get('content-length')}, "
            f"content-type={response.headers.get('content-type')}, url={url}"
        )
        response.raise_for_status()

        # Ensure directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        bytes_written = 0
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                bytes_written += len(chunk)

        # Verify file is not empty
        file_size = os.path.getsize(save_path)
        if file_size == 0:
            logger.error(f"Downloaded file is 0 bytes from {url} (bytes_written={bytes_written})")
            os.remove(save_path)
            return False

        logger.info(f"Downloaded {file_size} bytes from {url} to {save_path}")
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

    client_kwargs = {
        "aws_access_key_id": config.AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": config.AWS_SECRET_ACCESS_KEY,
        "region_name": config.AWS_REGION,
    }
    if config.AWS_ENDPOINT_URL:
        client_kwargs["endpoint_url"] = config.AWS_ENDPOINT_URL

    s3_client = boto3.client("s3", **client_kwargs)

    try:
        s3_client.upload_file(local_path, config.AWS_BUCKET_NAME, s3_key)

        if config.AWS_PUBLIC_URL_BASE:
            url = f"{config.AWS_PUBLIC_URL_BASE.rstrip('/')}/{s3_key}"
        elif config.AWS_ENDPOINT_URL:
            url = f"{config.AWS_ENDPOINT_URL.rstrip('/')}/{config.AWS_BUCKET_NAME}/{s3_key}"
        elif config.AWS_REGION == "us-east-1":
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
