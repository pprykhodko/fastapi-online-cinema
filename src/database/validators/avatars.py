from io import BytesIO
import warnings

from PIL import Image, UnidentifiedImageError


def validate_avatar(data: bytes, content_type: str) -> tuple[bytes, str]:
    formats = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png")}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(BytesIO(data)) as picture:
                if picture.format not in formats:
                    raise ValueError("Only JPEG and PNG images are allowed.")

                mime_type, extension = formats[picture.format]

                if content_type != mime_type:
                    raise ValueError("Content type does not match the image.")

                if max(picture.size) > 4096:
                    raise ValueError("Image dimensions must be <= 4096px.")

                if getattr(picture, "is_animated", False):
                    raise ValueError("Animated avatars are not supported.")

                picture.load()
                output = BytesIO()
                mode = "RGB" if extension == "jpg" else "RGBA"
                clean = picture.convert(mode)
                clean.info.clear()
                clean.save(output, format=picture.format)

                return output.getvalue(), extension

    except (
        UnidentifiedImageError, OSError, Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("The file is not a valid image.") from error
