from images.client import Photo, UnsplashClient
from images.frames import fill_empty_frames
from images.insert import apply_photos, find_slide_photos, replace_pictures_with_photos
from images.settings import UnsplashSettings

__all__ = [
    "Photo",
    "UnsplashClient",
    "UnsplashSettings",
    "apply_photos",
    "fill_empty_frames",
    "find_slide_photos",
    "replace_pictures_with_photos",
]
