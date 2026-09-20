from io import BytesIO
from unittest.mock import Mock

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from botocore.stub import Stubber  # type: ignore[import-untyped]
from PIL import Image, PngImagePlugin
import pytest

from src.core.config import Settings
from src.database.validators.avatars import validate_avatar
from src.storages.s3 import S3Storage, StorageError, get_s3_storage


@pytest.fixture
def storage_client(monkeypatch):
    client = Mock(spec=[
        "put_object", "generate_presigned_url", "delete_object", "close",
    ])
    factory = Mock(return_value=client)
    monkeypatch.setattr("src.storages.s3.boto3.client", factory)
    storage = S3Storage(Settings(
        _env_file=None, S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="test-access", S3_SECRET_KEY="test-secret",
    ))
    return storage, client, factory


def test_storage_upload_uses_private_object_and_explicit_credentials(
    storage_client,
):
    storage, client, factory = storage_client
    result = storage.upload_file(b"image", "avatars/1/a.png", "image/png")
    assert result is None
    client.put_object.assert_called_once_with(
        Bucket="avatars", Key="avatars/1/a.png", Body=b"image",
        ContentType="image/png",
    )
    options = factory.call_args.kwargs
    assert options["endpoint_url"] == "http://localhost:9000/"
    assert options["aws_access_key_id"] == "test-access"
    assert options["aws_secret_access_key"] == "test-secret"
    assert options["config"].signature_version == "s3v4"
    client.close.assert_called_once()


def test_storage_signed_url_and_delete(storage_client):
    storage, client, _ = storage_client
    client.generate_presigned_url.return_value = "https://s3.test/signed"
    assert storage.get_file_url("avatars/1/a.png") == "https://s3.test/signed"
    client.generate_presigned_url.assert_called_once_with(
        "get_object", Params={"Bucket": "avatars", "Key": "avatars/1/a.png"},
        ExpiresIn=3600,
    )
    storage.delete_file("avatars/1/a.png")
    client.delete_object.assert_called_once_with(
        Bucket="avatars", Key="avatars/1/a.png",
    )
    assert client.close.call_count == 2


@pytest.mark.parametrize("method,args,client_method", [
    ("upload_file", (b"image", "key", "image/png"), "put_object"),
    ("get_file_url", ("key",), "generate_presigned_url"),
    ("delete_file", ("key",), "delete_object"),
])
def test_storage_errors_are_wrapped(
    storage_client, method, args, client_method,
):
    storage, client, _ = storage_client
    getattr(client, client_method).side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "private"}},
        client_method,
    )
    with pytest.raises(StorageError) as error:
        getattr(storage, method)(*args)
    assert "private" not in str(error.value)
    client.close.assert_called_once()


@pytest.mark.parametrize("method", ["upload", "url", "delete"])
def test_real_boto3_client_is_closed_without_network(monkeypatch, method):
    storage = S3Storage(Settings(
        _env_file=None, S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="test-access", S3_SECRET_KEY="test-secret",
    ))
    client = storage._client()
    close = Mock(wraps=client.close)
    monkeypatch.setattr(client, "close", close)
    monkeypatch.setattr(storage, "_client", lambda **kwargs: client)
    with Stubber(client) as stubber:
        if method == "upload":
            stubber.add_response("put_object", {}, {
                "Bucket": "avatars", "Key": "key", "Body": b"image",
                "ContentType": "image/png",
            })
            storage.upload_file(b"image", "key", "image/png")
        elif method == "delete":
            stubber.add_response("delete_object", {}, {
                "Bucket": "avatars", "Key": "key",
            })
            storage.delete_file("key")
        else:
            url = storage.get_file_url("key")
            assert url.startswith("http://localhost:9000/avatars/key?")
            assert "X-Amz-Signature=" in url
        stubber.assert_no_pending_responses()
    close.assert_called_once()


def test_unconfigured_storage_does_not_use_metadata_credentials(monkeypatch):
    factory = Mock()
    monkeypatch.setattr("src.storages.s3.boto3.client", factory)
    storage = S3Storage(Settings(_env_file=None))
    with pytest.raises(StorageError, match="not configured"):
        storage.get_file_url("key")
    factory.assert_not_called()


def test_storage_dependency_is_lazy(monkeypatch):
    settings = Settings(_env_file=None)
    monkeypatch.setattr("src.storages.s3.get_settings", lambda: settings)
    assert get_s3_storage().settings is settings


@pytest.mark.parametrize("format,mime,extension", [
    ("PNG", "image/png", "png"), ("JPEG", "image/jpeg", "jpg"),
])
def test_avatar_decodes_and_strips_appended_data(format, mime, extension):
    source = BytesIO()
    Image.new("RGB", (5, 5), "blue").save(source, format=format)
    clean, suffix = validate_avatar(source.getvalue() + b"private-tail", mime)
    assert suffix == extension
    assert b"private-tail" not in clean
    with Image.open(BytesIO(clean)) as picture:
        picture.load()
        assert picture.size == (5, 5)


def test_avatar_strips_metadata():
    source = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "private location")
    picture = Image.new("RGB", (5, 5))
    picture.save(source, format="PNG", pnginfo=metadata)
    clean, _ = validate_avatar(source.getvalue(), "image/png")
    assert b"private location" not in clean


@pytest.mark.parametrize("format,mime,size", [
    ("GIF", "image/gif", (5, 5)),
    ("PNG", "image/jpeg", (5, 5)),
    ("PNG", "image/png", (4097, 1)),
])
def test_invalid_avatar_format_mime_and_dimensions(format, mime, size):
    source = BytesIO()
    Image.new("RGB", size).save(source, format=format)
    with pytest.raises(ValueError):
        validate_avatar(source.getvalue(), mime)


def test_corrupt_avatar_is_rejected():
    with pytest.raises(ValueError, match="not a valid image"):
        validate_avatar(b"not an image", "image/png")


def test_animated_png_is_rejected():
    source = BytesIO()
    picture = Image.new("RGB", (5, 5), "red")
    picture.save(
        source, format="PNG", save_all=True,
        append_images=[Image.new("RGB", (5, 5), "blue")],
    )
    with pytest.raises(ValueError, match="Animated"):
        validate_avatar(source.getvalue(), "image/png")
