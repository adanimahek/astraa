"""Evidence image storage.

Evidence is written below ``EVIDENCE_DIR`` (not the public ``/results`` mount)
and referenced in MongoDB by *relative* path.  It is served back only through
authenticated, ownership-checked endpoints.
"""
import os
import re
from pathlib import Path
from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_name(value: str, limit: int = 64) -> str:
    return _SAFE.sub("_", str(value))[:limit] or "item"


class EvidenceStore:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def folder(self, *parts: str) -> str:
        rel = os.path.join(*[safe_name(p) for p in parts])
        (self.root / rel).mkdir(parents=True, exist_ok=True)
        return rel

    def save_image(self, rel_folder: str, name: str, img: np.ndarray, quality: int = 90) -> str:
        rel = os.path.join(rel_folder, safe_name(name))
        if not cv2.imwrite(str(self.root / rel), img, [cv2.IMWRITE_JPEG_QUALITY, quality]):
            raise RuntimeError(f"Could not write evidence image {rel}")
        return rel.replace(os.sep, "/")

    def resolve(self, rel: str) -> Optional[Path]:
        """Resolve a stored relative path, refusing anything outside the root."""
        if not rel:
            return None
        path = (self.root / rel).resolve()
        if self.root not in path.parents or not path.is_file():
            return None
        return path

    def load(self, rel: str) -> Optional[np.ndarray]:
        path = self.resolve(rel)
        return cv2.imread(str(path)) if path else None


def crop(img: np.ndarray, box: Sequence[float], pad: float = 0.08) -> Optional[np.ndarray]:
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    x1, y1 = max(0, int(x1 - px)), max(0, int(y1 - py))
    x2, y2 = min(w, int(x2 + px)), min(h, int(y2 + py))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return img[y1:y2, x1:x2].copy()


def banner(img: np.ndarray, lines: Sequence[str], color: Tuple[int, int, int] = (0, 0, 200)) -> np.ndarray:
    out = img.copy()
    scale = max(0.45, min(out.shape[1] / 1400, 1.0))
    line_h = int(26 * scale) + 6
    cv2.rectangle(out, (0, 0), (out.shape[1], line_h * len(lines) + 8), color, -1)
    for i, text in enumerate(lines):
        cv2.putText(out, text, (8, line_h * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (255, 255, 255), max(1, int(2 * scale)), cv2.LINE_AA)
    return out
