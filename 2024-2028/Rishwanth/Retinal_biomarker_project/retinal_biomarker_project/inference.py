"""
inference.py — Multi-model inference and ensemble for vessel segmentation.

Provides:
    load_model()               — load any checkpoint (auto-detects arch)
    predict_single()           — run one image through one model
    ensemble_predict()         — average probability maps across models
    run_all_models_inference() — batch inference on all images in a folder
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from config import CFG
from preprocessing import build_multichannel
from augmentation import get_transforms


# ─────────────────────────────────────────────────────────────────────────────
# Model loader
# ─────────────────────────────────────────────────────────────────────────────

def load_model(checkpoint_path: str, device=None):
    """
    Load a model from a checkpoint saved by run_training_loop().

    Architecture is auto-detected from the checkpoint's 'arch' key:
        'AttentionUNet'     → models.attention_unet.AttentionUNet
        'UnetPlusPlusDS'    → models.unetplusplus.UnetPlusPlusDS
        'unetplusplus_scse' → models.unetplusplus_scse.build_unetplusplus_scse

    Args:
        checkpoint_path : path to .pt file
        device          : torch.device (default: CFG['device'])

    Returns:
        model : nn.Module in eval mode, on device
    """
    if device is None:
        device = CFG["device"]

    ckpt = torch.load(checkpoint_path, map_location=device)
    arch = ckpt.get("arch", "AttentionUNet")
    cfg  = ckpt.get("cfg",  CFG)

    n_ch = cfg.get("n_channels", 3)
    n_cl = cfg.get("n_classes",  1)

    if arch == "AttentionUNet":
        from models.attention_unet import AttentionUNet
        model = AttentionUNet(n_channels=n_ch, n_classes=n_cl)

    elif arch == "UnetPlusPlusDS":
        from models.unetplusplus import UnetPlusPlusDS
        encoder = ckpt.get("encoder", "resnet34")
        model   = UnetPlusPlusDS(n_channels=n_ch, n_classes=n_cl, encoder=encoder)

    elif arch == "unetplusplus_scse":
        from models.unetplusplus_scse import build_unetplusplus_scse
        encoder = ckpt.get("encoder", "resnet34")
        model   = build_unetplusplus_scse(n_channels=n_ch, n_classes=n_cl,
                                          encoder=encoder, weights=None)
    else:
        raise ValueError(
            f"Unknown arch '{arch}' in checkpoint. "
            "Expected: AttentionUNet | UnetPlusPlusDS | unetplusplus_scse"
        )

    model.load_state_dict(ckpt["model_state"])
    model = model.to(device)
    model.eval()
    print(f"Loaded {arch} from '{checkpoint_path}'  "
          f"(epoch={ckpt.get('epoch','?')}  best_dice={ckpt.get('best_dice',0):.4f})")
    return model


# ─────────────────────────────────────────────────────────────────────────────
# Single-image prediction
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def predict_single(model,
                   bgr_image: np.ndarray,
                   device=None,
                   return_size: tuple | None = None) -> np.ndarray:
    """
    Run one model on one BGR fundus image.

    Args:
        model        : nn.Module in eval mode
        bgr_image    : (H, W, 3) uint8  BGR from cv2.imread
        device       : torch.device (default: CFG['device'])
        return_size  : (H_orig, W_orig) — if provided, resize output back.
                       Pass None to return at CFG['img_size'] resolution.

    Returns:
        prob_map : (H, W) float32 [0, 1]  — sigmoid probability map
                   at return_size resolution if specified, else img_size.
    """
    if device is None:
        device = CFG["device"]

    val_tf   = get_transforms("val")
    multi    = build_multichannel(bgr_image)        # (H, W, 3) uint8
    aug      = val_tf(image=multi, mask=np.zeros(multi.shape[:2], np.float32))
    img_t    = aug["image"].unsqueeze(0).float().to(device)  # (1,3,H,W)

    model.eval()
    logit = model(img_t)
    if isinstance(logit, tuple):
        logit = logit[0]                            # main head only

    prob = torch.sigmoid(logit).squeeze().cpu().numpy()  # (H, W) float32

    if return_size is not None:
        H_orig, W_orig = return_size
        prob = cv2.resize(prob, (W_orig, H_orig), interpolation=cv2.INTER_LINEAR)

    return prob.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Ensemble
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def ensemble_predict(models: list,
                     bgr_image: np.ndarray,
                     device=None,
                     return_size: tuple | None = None) -> np.ndarray:
    """
    Average probability maps from multiple models (simple mean ensemble).

    Args:
        models       : list of nn.Module (each in eval mode)
        bgr_image    : (H, W, 3) uint8 BGR
        device       : torch.device
        return_size  : (H_orig, W_orig) for final resize

    Returns:
        prob_map : (H, W) float32 [0, 1] — averaged probabilities
    """
    if device is None:
        device = CFG["device"]

    probs = [predict_single(m, bgr_image, device=device, return_size=return_size)
             for m in models]
    return np.mean(probs, axis=0).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Batch inference
# ─────────────────────────────────────────────────────────────────────────────

def run_all_models_inference(
    image_dir:        str,
    checkpoint_paths: list[str],
    output_dir:       str = "segmentation_outputs",
    threshold:        float = 0.5,
    save_prob_maps:   bool  = True,
):
    """
    Run ensemble inference on every image in image_dir.

    For each image:
        1. Runs all checkpoints and averages probabilities.
        2. Thresholds to binary mask.
        3. Saves probability map and binary mask as PNG.

    Args:
        image_dir        : folder containing fundus images
        checkpoint_paths : list of .pt checkpoint paths (any mix of arch types)
        output_dir       : where to write results
        threshold        : binarisation threshold (default 0.5)
        save_prob_maps   : also save float32 prob map as 8-bit gray PNG

    Returns:
        results : dict  image_name → {'prob_map': np.ndarray,
                                       'binary_mask': np.ndarray}
    """
    from postprocessing import postprocess_mask

    _IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".ppm"}
    out_dir  = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    device = CFG["device"]
    print(f"Loading {len(checkpoint_paths)} model(s) …")
    models = [load_model(cp, device=device) for cp in checkpoint_paths]

    img_paths = sorted([p for p in Path(image_dir).iterdir()
                        if p.suffix.lower() in _IMG_EXT])
    if not img_paths:
        raise FileNotFoundError(f"No images found in {image_dir}")

    print(f"Running ensemble inference on {len(img_paths)} images …")
    results = {}

    for img_path in img_paths:
        bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if bgr is None:
            print(f"  [SKIP] Cannot read {img_path.name}")
            continue

        H_orig, W_orig = bgr.shape[:2]
        prob_map     = ensemble_predict(models, bgr, device=device,
                                        return_size=(H_orig, W_orig))
        binary_mask  = postprocess_mask(prob_map, threshold=threshold)

        if save_prob_maps:
            prob_gray = (prob_map * 255).clip(0, 255).astype(np.uint8)
            cv2.imwrite(str(out_dir / f"{img_path.stem}_prob.png"), prob_gray)

        cv2.imwrite(str(out_dir / f"{img_path.stem}_mask.png"), binary_mask)

        results[img_path.name] = {
            "prob_map":    prob_map,
            "binary_mask": binary_mask,
        }
        print(f"  {img_path.name}  →  vessel_px: "
              f"{(binary_mask > 0).sum()}  "
              f"({100*(binary_mask>0).mean():.1f}%)")

    print(f"\nDone. Results saved to '{output_dir}/'")
    return results
