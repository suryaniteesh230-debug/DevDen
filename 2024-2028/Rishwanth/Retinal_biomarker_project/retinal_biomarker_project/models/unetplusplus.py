"""
models/unetplusplus.py — UNet++ with ResNet34 encoder and deep supervision.

Provides:
    UnetPlusPlusDS — UNet++ (ResNet34-imagenet) with hook-based deep supervision.
        Training mode  → (main_logit, [aux0, aux1, aux2])
        Eval / infer   → main_logit  only

Architecture:
    Encoder  : ResNet34, pre-trained on ImageNet
    Decoder  : UNet++ nested skip-connections (smp.UnetPlusPlus)
    Deep sup : one auxiliary 1×1 conv head per decoder scale
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    import segmentation_models_pytorch as smp
except ModuleNotFoundError as _smp_err:
    raise ModuleNotFoundError(
        "segmentation_models_pytorch is not installed.\n\n"
        "Fix: Run config.py first — it auto-installs the package.\n"
    ) from _smp_err

from config import CFG


class UnetPlusPlusDS(nn.Module):
    """
    UNet++ with ResNet34 encoder and deep supervision.

    Architecture:
        Encoder  : ResNet34, pre-trained on ImageNet
        Decoder  : UNet++ nested skip-connections (smp.UnetPlusPlus)
        Deep sup : one auxiliary 1×1 conv head per decoder scale
                   (scales ×2, ×4, ×8 relative to bottleneck)

    Forward output:
        Training mode  → (main_logit, [aux_logit_s2, aux_logit_s3, aux_logit_s4])
        Eval / infer   → main_logit  only

    All logits are bilinearly upsampled to input resolution (H, W) before
    returning so that the loss always receives (B, 1, H, W) tensors.

    Args:
        n_channels  : input channels (3 for green|CLAHE|Retinex stack)
        n_classes   : output classes (1 for binary vessel segmentation)
        encoder     : SMP encoder name (default: 'resnet34')
        weights     : encoder pre-training  (default: 'imagenet')
    """

    def __init__(
        self,
        n_channels: int = 3,
        n_classes:  int = 1,
        encoder:    str = "resnet34",
        weights:    str = "imagenet",
    ):
        super().__init__()

        # ── Base UNet++ from SMP ──────────────────────────────────────────────
        self.base = smp.UnetPlusPlus(
            encoder_name         = encoder,
            encoder_weights      = weights,
            in_channels          = n_channels,
            classes              = n_classes,
            decoder_channels     = (256, 128, 64, 32, 16),
            decoder_use_batchnorm=True,
        )

        self.n_classes = n_classes

        # ── Probe decoder blocks and build aux heads dynamically ───────────────
        if not hasattr(self.base.decoder, "blocks"):
            raise AttributeError(
                f"smp {smp.__version__}: UnetPlusPlus.decoder has no attribute "
                "'blocks'. Deep supervision cannot be wired. "
                "Tested on smp 0.3.x — check your version."
            )

        blocks_container = self.base.decoder.blocks

        if hasattr(blocks_container, "values"):
            _all_block_modules = list(blocks_container.values())   # ModuleDict
        else:
            _all_block_modules = list(blocks_container)            # ModuleList

        if len(_all_block_modules) < 5:
            raise RuntimeError(
                f"Expected ≥5 decoder blocks for ResNet34+UNet++, "
                f"got {len(_all_block_modules)}. "
                "Architecture changed — check your smp version."
            )

        def _block_out_channels(block: nn.Module) -> int:
            """
            Introspect a decoder block's output channel count by scanning its
            child modules for the last Conv2d or BatchNorm2d weight shape.
            Returns -1 if nothing found.
            """
            last_ch = -1
            for m in block.modules():
                if isinstance(m, nn.Conv2d):
                    last_ch = m.out_channels
                elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                    last_ch = m.num_features
            return last_ch

        # Sort blocks by output channels DESCENDING → deepest (widest) first.
        _blocks_with_ch = [
            (b, _block_out_channels(b)) for b in _all_block_modules
        ]
        _blocks_with_ch.sort(key=lambda t: t[1], reverse=True)

        # Pick the 3 blocks with the highest output channel counts as deep
        # supervision taps (one per scale, deduplicated by channel count).
        seen_ch: set = set()
        _ds_blocks: list = []
        _ds_channels: list = []
        for blk, ch in _blocks_with_ch:
            if ch not in seen_ch and ch > 0:
                seen_ch.add(ch)
                _ds_blocks.append(blk)
                _ds_channels.append(ch)
            if len(_ds_blocks) == 3:
                break

        if len(_ds_blocks) < 3:
            raise RuntimeError(
                f"Could not identify 3 distinct decoder scale blocks for deep "
                f"supervision. Found {len(_ds_blocks)}: {_ds_channels}. "
                "Check smp version / decoder architecture."
            )

        self._ds_blocks   = _ds_blocks    # list of 3 nn.Module (deepest first)
        self._ds_channels = _ds_channels  # list of 3 int — actual output ch

        # Build aux heads with CORRECT input channels (introspected, not assumed).
        self.aux_heads = nn.ModuleList([
            nn.Conv2d(ch, n_classes, kernel_size=1) for ch in _ds_channels
        ])

        print(
            f"[UnetPlusPlusDS] smp {smp.__version__}  |  "
            f"decoder.blocks type: {type(blocks_container).__name__}  |  "
            f"{len(_all_block_modules)} blocks total.\n"
            f"  Deep supervision taps: {_ds_channels} ch  "
            f"(introspected, deepest→shallowest)"
        )

    def forward(self, x: torch.Tensor):
        """
        Args:
            x : (B, n_channels, H, W) float tensor, normalised to [-1,1]

        Returns:
            Training   : (main_logit, [aux0, aux1, aux2])
                         All tensors (B, n_classes, H, W), raw logits.
            Eval/infer : main_logit  (B, n_classes, H, W), raw logits.
        """
        H, W = x.shape[2], x.shape[3]

        # In eval/inference mode: just run the base model — no hooks needed.
        if not self.training:
            main_logit = self.base(x)   # (B, n_classes, H, W)
            if main_logit.shape[2:] != (H, W):
                main_logit = F.interpolate(
                    main_logit, size=(H, W), mode="bilinear", align_corners=False
                )
            return main_logit

        # ── Training mode: register hooks on the 3 deepest decoder blocks ──────
        _hook_outputs: list = []

        def _make_hook():
            def _hook(module, inp, out):
                _hook_outputs.append(out)
            return _hook

        _handles = [
            blk.register_forward_hook(_make_hook())
            for blk in self._ds_blocks
        ]

        try:
            main_logit = self.base(x)   # runs full encoder + decoder + seg head
        finally:
            # Always remove hooks — even if forward raises an exception.
            for h in _handles:
                h.remove()

        # Ensure main output matches input resolution.
        if main_logit.shape[2:] != (H, W):
            main_logit = F.interpolate(
                main_logit, size=(H, W), mode="bilinear", align_corners=False
            )

        # ── Auxiliary heads for deep supervision ─────────────────────────────
        aux_logits = []
        for i, head in enumerate(self.aux_heads):
            feat = _hook_outputs[i]
            aux  = head(feat)
            if aux.shape[2:] != (H, W):
                aux = F.interpolate(
                    aux, size=(H, W), mode="bilinear", align_corners=False
                )
            aux_logits.append(aux)

        return main_logit, aux_logits
