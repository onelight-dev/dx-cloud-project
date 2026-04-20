import os
import uuid
from io import BytesIO
import paramiko
from config.sftp import SFTP_CONFIG, SFTP_BASE_DIR, SFTP_BASE_URL

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _make_remote_path(filename: str) -> str:
    """원격 파일의 절대 경로를 생성합니다."""
    return f"{SFTP_BASE_DIR}/{filename}"


def _make_public_url(filename: str) -> str:
    """공개 URL을 생성합니다. SFTP_BASE_URL이 설정되지 않으면 경로 그대로 반환합니다."""
    base = SFTP_BASE_URL.rstrip("/")
    return f"{base}/{filename}" if base else _make_remote_path(filename)


def _get_sftp_client() -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(**SFTP_CONFIG)
    sftp = ssh.open_sftp()
    return ssh, sftp


def _ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    """원격 디렉터리가 없으면 재귀적으로 생성합니다."""
    parts = remote_dir.split("/")
    current = ""
    for part in parts:
        if not part:
            current = "/"
            continue
        current = f"{current}/{part}" if current != "/" else f"/{part}"
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def upload_image(file_storage) -> str:
    """Flask FileStorage 객체를 SFTP 서버에 업로드하고 공개 URL을 반환합니다.

    Args:
        file_storage: Flask request.files 에서 가져온 FileStorage 객체

    Returns:
        업로드된 이미지의 공개 URL 문자열

    Raises:
        ValueError: 허용되지 않는 파일 형식인 경우
        paramiko.SSHException: SFTP 연결 오류
    """
    if not file_storage or not file_storage.filename:
        raise ValueError("파일이 제공되지 않았습니다.")

    if not _allowed_file(file_storage.filename):
        raise ValueError(f"허용되지 않는 파일 형식입니다. 허용 형식: {', '.join(ALLOWED_EXTENSIONS)}")

    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    remote_path = _make_remote_path(unique_name)

    data = BytesIO(file_storage.read())

    ssh, sftp = _get_sftp_client()
    try:
        _ensure_remote_dir(sftp, SFTP_BASE_DIR)
        sftp.putfo(data, remote_path)
    finally:
        sftp.close()
        ssh.close()

    return _make_public_url(unique_name)


def delete_image(image_url: str) -> None:
    """SFTP 서버에서 이미지를 삭제합니다.

    Args:
        image_url: upload_image()가 반환한 URL 또는 원격 경로

    Raises:
        FileNotFoundError: 원격 파일이 존재하지 않는 경우
        paramiko.SSHException: SFTP 연결 오류
    """
    # URL에서 파일명만 추출
    filename = image_url.split("/")[-1]
    remote_path = _make_remote_path(filename)

    ssh, sftp = _get_sftp_client()
    try:
        sftp.remove(remote_path)
    finally:
        sftp.close()
        ssh.close()
