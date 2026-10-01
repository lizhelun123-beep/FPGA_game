"""Small ROI operations for physical outlines and dark-body contrast."""
import cv2
import numpy as np


def source_outline(body, dark_mask, config):
    """Recover only a closed dark outline enclosing the color seed.

    No rectangle expansion and no vertex-count gate: an incomplete border leaves
    the original body unchanged rather than inventing its missing tip.
    """
    x, y, w, h = cv2.boundingRect(body)
    padding = max(2, int(round(max(w, h) * config["padding_fraction"])))
    x0, y0 = max(0, x-padding), max(0, y-padding)
    x1, y1 = min(dark_mask.shape[1], x+w+padding), min(dark_mask.shape[0], y+h+padding)
    roi = dark_mask[y0:y1, x0:x1]
    offset = np.array([[[x0, y0]]], np.int32)
    seed = np.zeros_like(roi)
    cv2.drawContours(seed, [body-offset], -1, 255, -1)
    seed_pixels = max(cv2.countNonZero(seed), 1)
    body_area = cv2.contourArea(body)
    found, hierarchy = cv2.findContours(roi, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return body, False
    best, best_area = None, float("inf")
    for i, outer in enumerate(found):
        if hierarchy[0, i, 3] != -1:
            continue
        area = cv2.contourArea(outer)
        if not body_area < area <= body_area * config["max_area_growth"] or area >= best_area:
            continue
        ox, oy, ow, oh = cv2.boundingRect(outer)
        if ox == 0 or oy == 0 or ox+ow == roi.shape[1] or oy+oh == roi.shape[0]:
            continue
        child = hierarchy[0, i, 2]
        while child != -1:
            hole = np.zeros_like(roi)
            cv2.drawContours(hole, [found[child]], -1, 255, -1)
            overlap = cv2.countNonZero(hole & seed) / seed_pixels
            if overlap >= config["min_hole_overlap"]:
                best, best_area = outer+offset, area
                break
            child = hierarchy[0, child, 0]
    return (best, True) if best is not None else (body, False)


def wall_contrast(hsv, contour, config):
    """Median V outside the bbox minus median V inside the filled contour."""
    x, y, w, h = cv2.boundingRect(contour)
    (_, _), (rw, rh), _ = cv2.minAreaRect(contour)
    padding = max(2, int(round(min(rw, rh) * config["surround_fraction"])))
    x0, y0 = max(0, x-padding), max(0, y-padding)
    x1, y1 = min(hsv.shape[1], x+w+padding), min(hsv.shape[0], y+h+padding)
    values = hsv[y0:y1, x0:x1, 2]
    outer = np.ones(values.shape, dtype=bool)
    outer[y-y0:y-y0+h, x-x0:x-x0+w] = False
    if np.count_nonzero(outer) < config["min_surround_pixels"]:
        return None
    inner = np.zeros(values.shape, np.uint8)
    cv2.drawContours(inner, [contour-np.array([[[x0, y0]]], np.int32)], -1, 255, -1)
    return float(np.median(values[outer]) - np.median(values[inner != 0]))
