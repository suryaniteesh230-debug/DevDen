# Duplicate Code Removal Log

All four notebooks contained overlapping code across preprocessing, dataset loading, augmentation, training loops, and loss functions.
Below is every duplicate removed and the single canonical location it now lives.

---

## 1. `seed_everything()` function

**Found in:** `attention-u-net.ipynb`, `v5-unet_plusplus.ipynb`, `unetplusplus-with-attention-gates.ipynb`, `full-end-to-end.ipynb`

**Moved to:** `config.py`

---

## 2. `CFG` dict  +  `ROOT_DIR`  +  `SEG_SUBSETS`

**Found in:** All 4 notebooks (identical or near-identical)

**Moved to:** `config.py`

---

## 3. `single_scale_retinex()` + `build_multichannel()`

**Found in:** All 4 notebooks

**Moved to:** `preprocessing.py`

---

## 4. `get_transforms()` (albumentations pipeline)

**Found in:** All 4 notebooks (identical train and val pipelines)

**Moved to:** `augmentation.py`

---

## 5. `RetinalDataset` + `AugmentedDataset` + `ValDataset` + `_IndexedSubset` + `build_loaders()`

**Found in:** `attention-u-net.ipynb`, `v5-unet_plusplus.ipynb`, `unetplusplus-with-attention-gates.ipynb` (copy-pasted with minor name variations)

**Moved to:** `dataset.py`

---

## 6. `TverskyLoss` + `FocalTverskyLoss`

**Found in:** All 4 notebooks

**Moved to:** `training.py`

---

## 7. `CombinedLoss` (BCE + FocalTversky)

**Found in:** `attention-u-net.ipynb`, `unetplusplus-with-attention-gates.ipynb`, `full-end-to-end.ipynb` (used for Attention U-Net and UNet++SCSE)

**Moved to:** `training.py`

---

## 8. `SoftSkeletonize` + `clDiceLoss` + `CombinedLossWithClDice`

**Found in:** `v5-unet_plusplus.ipynb`, `full-end-to-end.ipynb`

**Moved to:** `training.py`

---

## 9. `train_one_epoch()` + `validate()` + `run_training_loop()`

**Found in:** All 4 notebooks (identical except for the `deep_supervision` flag, which is now a parameter)

**Moved to:** `training.py` — `deep_supervision=True/False` parameter controls UNet++DS behaviour

---

## 10. `DoubleConv` block

**Found in:** `attention-u-net.ipynb`, `full-end-to-end.ipynb`

**Moved to:** `models/attention_unet.py`

---

## 11. `compute_width_map()` / `compute_width_map_local()`

**Found in:** `full-end-to-end.ipynb` (defined twice — once as `compute_width_map`, once inline as a distance-transform)

**Moved to:**
- `av_segments.py` → `compute_width_map()` (used in segment extraction)
- `biomarkers.py`  → `compute_width_map_local()` (used in biomarker calculations)

Both are identical implementations; the two names are kept to avoid a cross-import between `av_segments` and `biomarkers`.

---

## 12. `decode_av_label_drive()` + `decode_av_label_les()`

**Found in:** `full-end-to-end.ipynb` (inline, called from multiple cells)

**Moved to:** `av_dataset.py`

---

## 13. `_segment_orientation()` + `_segment_mean_width()` + `_angle_diff()`

**Found in:** `full-end-to-end.ipynb` (used in both segment merging and patch extraction)

**Moved to:** `av_segments.py`

---

## 14. `labels_to_masks()`

**Found in:** `full-end-to-end.ipynb` (called from visualisation and biomarker cells)

**Moved to:** `av_visualisation.py` — imported by `biomarkers.py`

---

## 15. `render_av_overlay()` / `_av_overlay_image()`

**Found in:** `full-end-to-end.ipynb` (two near-identical overlay renderers in separate cells)

**Moved to:**
- `biomarkers.py` → `render_av_overlay()` (used inside `visualise_results()`)
- `run_av_pipeline.py` → `_av_overlay_image()` (lightweight inline helper for file saves)

The two differ only in blending weights; both are retained to preserve exact original behaviour.

---

## 16. All postprocessing functions (`postprocess_mask`, `skeletonize_mask`, `skeleton_to_graph`, `full_postprocess_pipeline`)

**Found in:** `full-end-to-end.ipynb` and partially in the individual segmentation notebooks

**Moved to:** `postprocessing.py`

---

## 17. `load_model()` (checkpoint loader)

**Found in:** `full-end-to-end.ipynb` (instantiated inline per model type, duplicated per model)

**Moved to:** `inference.py` — single function auto-detects arch from checkpoint

---

## 18. `predict_single()` + `ensemble_predict()`

**Found in:** `full-end-to-end.ipynb`

**Moved to:** `inference.py`

---

## Summary

| Category | # Duplicates removed | Canonical file |
|---|---|---|
| Config / seed | 4× | `config.py` |
| Preprocessing | 4× | `preprocessing.py` |
| Augmentation | 4× | `augmentation.py` |
| Dataset loading | 3× | `dataset.py` |
| Loss functions | 4× | `training.py` |
| Training loop | 4× | `training.py` |
| Postprocessing | 2× | `postprocessing.py` |
| Inference | 2× | `inference.py` |
| AV dataset loading | 1× inline → module | `av_dataset.py` |
| Segment geometry | 1× inline → module | `av_segments.py` |
| Width map | 2× inline → 2 modules | `av_segments.py`, `biomarkers.py` |
| Overlay renderer | 2× near-identical | `biomarkers.py`, `run_av_pipeline.py` |
| labels_to_masks | 1× inline → module | `av_visualisation.py` |
| Model definitions | spread across 4 notebooks | `models/` package |
