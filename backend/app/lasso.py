"""
Server-side lasso -> mask -> crop pipeline (Slice A).

The frontend only ever sends polygon points in CANVAS-display pixel space plus
the canvas size it drew at. All real pixel math (scaling to the true image,
rasterizing the mask, cropping, applying transparency) happens here.
"""
import numpy as np
import cv2
from PIL import Image


def polygon_to_crop(image: Image.Image, polygon: list[list[float]], canvas_w: float, canvas_h: float):
    """
    Scale a canvas-space polygon to true image pixels, rasterize a mask,
    crop to the polygon's bounding box, and apply the mask (outside -> transparent).

    Returns (crop_rgba: PIL.Image, mask: np.ndarray uint8, bbox: (x0,y0,x1,y1) in true image px).
    """
    img_w, img_h = image.size
    sx = img_w / canvas_w
    sy = img_h / canvas_h

    scaled = np.array([[p[0] * sx, p[1] * sy] for p in polygon], dtype=np.float64)
    if len(scaled) < 3:
        raise ValueError("polygon needs at least 3 points")

    pts_int = np.round(scaled).astype(np.int32)

    full_mask = np.zeros((img_h, img_w), dtype=np.uint8)
    cv2.fillPoly(full_mask, [pts_int], 255)

    x0, y0 = pts_int[:, 0].min(), pts_int[:, 1].min()
    x1, y1 = pts_int[:, 0].max(), pts_int[:, 1].max()
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img_w, x1), min(img_h, y1)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("polygon bounding box is degenerate")

    mask_crop = full_mask[y0:y1, x0:x1]

    rgba = image.convert("RGBA")
    arr = np.array(rgba)[y0:y1, x0:x1].copy()
    arr[:, :, 3] = mask_crop  # outside polygon -> alpha 0 (transparent)

    crop_rgba = Image.fromarray(arr, mode="RGBA")
    return crop_rgba, mask_crop, (int(x0), int(y0), int(x1), int(y1))
