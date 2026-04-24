import uuid
import boto3
from botocore.exceptions import ClientError
from config.s3 import (
    S3_BUCKET_NAME, S3_REGION, S3_PUBLIC_URL,
    S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY,
)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}


def _get_ext(filename: str) -> str:
    """허용된 확장자를 검증하고 반환합니다."""
    if not filename or "." not in filename:
        raise ValueError("파일이 제공되지 않았습니다.")
    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"허용되지 않는 파일 형식입니다. 허용 형식: {', '.join(ALLOWED_EXTENSIONS)}")
    return f".{ext}"


def _get_s3_client():
    """boto3 S3 클라이언트를 반환합니다.

    - MinIO(로컬): S3_ENDPOINT_URL + 명시적 자격증명 사용
    - AWS EKS:     endpoint_url 미설정 → IRSA(IAM Role) 자동 인증
    """
    kwargs: dict = {"region_name": S3_REGION}
    if S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = S3_ENDPOINT_URL
    if S3_ACCESS_KEY and S3_SECRET_KEY:
        kwargs["aws_access_key_id"]     = S3_ACCESS_KEY
        kwargs["aws_secret_access_key"] = S3_SECRET_KEY
    return boto3.client("s3", **kwargs)


def upload_image(file_storage) -> str:
    """Flask FileStorage 객체를 S3(또는 MinIO)에 업로드하고 공개 URL을 반환합니다.

    Args:
        file_storage: Flask request.files 에서 가져온 FileStorage 객체

    Returns:
        업로드된 이미지의 공개 URL 문자열

    Raises:
        ValueError: 파일 없음 또는 허용되지 않는 확장자
        ClientError: S3 업로드 오류
    """
    ext = _get_ext(file_storage.filename)
    key = f"{uuid.uuid4().hex}{ext}"

    content_type = (
        file_storage.content_type
        if file_storage.content_type and file_storage.content_type != "application/octet-stream"
        else f"image/{ext.lstrip('.')}"
    )

    s3 = _get_s3_client()
    s3.upload_fileobj(
        file_storage.stream,
        S3_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": content_type},
    )

    return f"{S3_PUBLIC_URL}/{key}"


def delete_image(image_url: str) -> None:
    """S3(또는 MinIO)에서 이미지를 삭제합니다.

    Args:
        image_url: upload_image()가 반환한 공개 URL

    Raises:
        ClientError: S3 삭제 오류
    """
    prefix = S3_PUBLIC_URL + "/"
    key = image_url[len(prefix):] if image_url.startswith(prefix) else image_url.split("/")[-1]

    s3 = _get_s3_client()
    s3.delete_object(Bucket=S3_BUCKET_NAME, Key=key)
