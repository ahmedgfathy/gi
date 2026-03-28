"""
Core perception module.
Handles text, image, and multimodal input encoding using pretrained models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np


# Text Perception

class TextEncoder:
    """
    Encodes raw text into dense semantic embeddings.
    Uses sentence-transformers (all-MiniLM-L6-v2 by default — 384-dim, fast).
    """

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        except ImportError:
            raise ImportError("sentence-transformers is required. Run: pip install sentence-transformers")

    def encode(self, texts: Union[str, list[str]]) -> np.ndarray:
        if self._model is None:
            self._load()
        if isinstance(texts, str):
            texts = [texts]
        return self._model.encode(texts, normalize_embeddings=True)


# Image Perception

class ImageEncoder:
    """
    Encodes images into feature vectors using a pretrained ViT from timm.
    Default: vit_small_patch16_224 (~22M params).
    """

    DEFAULT_MODEL = "vit_small_patch16_224"

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self._transforms = None

    def _load(self) -> None:
        try:
            import timm
            import torch
            self._model = timm.create_model(self.model_name, pretrained=True, num_classes=0)
            self._model.eval()
            data_cfg = timm.data.resolve_model_data_config(self._model)
            self._transforms = timm.data.create_transform(**data_cfg, is_training=False)
        except ImportError:
            raise ImportError("timm and torch are required. Run: pip install timm torch")

    def encode(self, image_path: Union[str, Path]) -> np.ndarray:
        if self._model is None:
            self._load()
        import torch
        from PIL import Image
        img = Image.open(image_path).convert("RGB")
        tensor = self._transforms(img).unsqueeze(0)
        with torch.no_grad():
            features = self._model(tensor)
        return features.numpy().squeeze()


# Multimodal Fusion

def fuse(embeddings: list[np.ndarray], method: str = "concat") -> np.ndarray:
    """
    Fuse multiple modality embeddings into one joint representation.
    Methods: concat | mean | sum
    """
    if method == "concat":
        return np.concatenate(embeddings, axis=-1)
    elif method == "mean":
        return np.mean(np.stack(embeddings), axis=0)
    elif method == "sum":
        return np.sum(np.stack(embeddings), axis=0)
    else:
        raise ValueError(f"Unknown fusion method: {method}")
