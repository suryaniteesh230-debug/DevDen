"""
postprocessing.py — Post-processing, skeletonization, and graph modeling.

Provides:
    postprocess_mask()           — single-threshold + min-area + endpoint bridging
    skeletonize_mask()           — 1-pixel-wide medial-axis skeleton
    skeleton_to_graph()          — NetworkX vessel graph from skeleton
    full_postprocess_pipeline()  — end-to-end: prob_map → mask + skeleton + graph
    visualise_graph()            — 3-panel plot of fundus, mask, skeleton+graph

Pipeline:
    1. Single threshold 0.5     — clean binary from well-trained model
    2. Min-area filter (30px)   — removes isolated noise pixels only
    3. Skeleton-guided gap repair — bridges only true broken endpoints
    4. Final min-area filter    — cleans any residual single-pixel noise
"""
from __future__ import annotations

import cv2
import numpy as np
import matplotlib.pyplot as plt

try:
    from skimage.morphology import skeletonize
    from skimage.measure    import label, regionprops
    import networkx as nx
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False
    print("[WARNING] skimage / networkx not found. "
          "Run:  pip install scikit-image networkx")


# ─────────────────────────────────────────────────────────────────────────────
# Post-processing internals
# ─────────────────────────────────────────────────────────────────────────────

def _find_skeleton_endpoints(skeleton: np.ndarray):
    """
    Returns list of (row, col) coordinates of skeleton endpoints.
    An endpoint is a skeleton pixel with exactly 1 eight-connected neighbour.
    """
    skel = skeleton.astype(bool)
    pts  = np.argwhere(skel)
    H, W = skel.shape
    endpoints = []
    for (r, c) in pts:
        n = 0
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < H and 0 <= nc < W and skel[nr, nc]:
                    n += 1
        if n == 1:
            endpoints.append((r, c))
    return endpoints


def _bridge_endpoints(clean: np.ndarray,
                      prob_map: np.ndarray,
                      gap_px: int = 7,
                      prob_threshold: float = 0.5) -> np.ndarray:
    """
    Skeleton-guided endpoint-only gap bridging.

    Algorithm:
        1. Skeletonize the current binary mask.
        2. Find all skeleton endpoints (degree-1 pixels).
        3. For each pair of endpoints within gap_px pixels of each other:
             a. Check that the straight-line path between them passes through
                pixels whose probability is BELOW prob_threshold.
                (If prob is HIGH between them, they are two sides of a vessel
                crossing — do NOT bridge. If prob is LOW, there is a true gap.)
             b. If it is a true gap: draw a 1px-wide line connecting them.
        4. Return the patched binary mask.

    Args:
        clean          : (H, W) uint8 {0,255} binary mask after min-area filter
        prob_map       : (H, W) float32 [0,1] original probability map
        gap_px         : maximum endpoint-to-endpoint distance to attempt bridging
        prob_threshold : if mean prob along the line ≥ this, skip (it's a crossing)

    Returns:
        (H, W) uint8 patched mask
    """
    if not _DEPS_OK:
        return clean  # skimage required for skeletonization

    skel      = skeletonize((clean > 0).astype(bool))
    endpoints = _find_skeleton_endpoints(skel)

    if len(endpoints) < 2:
        return clean

    result = clean.copy()

    ep_arr = np.array(endpoints, dtype=np.float32)
    n      = len(ep_arr)

    for i in range(n):
        r1, c1 = int(ep_arr[i, 0]), int(ep_arr[i, 1])
        for j in range(i + 1, n):
            r2, c2 = int(ep_arr[j, 0]), int(ep_arr[j, 1])

            dist = np.hypot(r2 - r1, c2 - c1)
            if dist > gap_px:
                continue

            # Sample the probability along the straight line between endpoints
            n_samples = max(int(dist) + 1, 2)
            rs = np.linspace(r1, r2, n_samples).astype(int).clip(0, prob_map.shape[0] - 1)
            cs = np.linspace(c1, c2, n_samples).astype(int).clip(0, prob_map.shape[1] - 1)
            mean_prob = prob_map[rs, cs].mean()

            # Only bridge if mean probability along the gap is LOW.
            # High mean prob = the gap is inside a vessel crossing → skip.
            # Low mean prob = true broken endpoint → bridge.
            if mean_prob >= prob_threshold:
                continue  # crossing — skip

            # Draw a 1-pixel-wide line connecting the two endpoints
            cv2.line(result, (c1, r1), (c2, r2), 255, thickness=1)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public post-processing function
# ─────────────────────────────────────────────────────────────────────────────

def postprocess_mask(prob_map: np.ndarray,
                     threshold:  float = 0.5,
                     min_area:   int   = 30,
                     gap_px:     int   = 7) -> np.ndarray:
    """
    Post-processing that trusts the model output and cleans minimally.

    Pipeline:
        1. Single threshold at 0.5     — clean binary from trained model
        2. Min-area filter (30px)      — removes noise, keeps all true vessels
        3. Skeleton-guided endpoint    — bridges only true broken endpoints,
           gap bridging                 correctly skips vessel crossings
        4. Final min-area filter (10px)— removes any residual noise from bridging

    Args:
        prob_map  : (H, W) float32 [0,1]  — sigmoid output of model
        threshold : vessel probability cutoff (default 0.5)
        min_area  : minimum component area to keep in step 2 (default 30)
        gap_px    : maximum gap between endpoints to attempt bridging (default 7)

    Returns:
        (H, W) uint8 binary mask {0, 255}
    """
    # ── Step 1: Single threshold ──────────────────────────────────────────────
    binary = ((prob_map >= threshold) * 255).astype(np.uint8)

    # ── Step 2: Min-area filter — remove isolated noise pixels ───────────────
    n_labels, label_map, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    clean = np.zeros_like(binary)
    for lbl in range(1, n_labels):
        if stats[lbl, cv2.CC_STAT_AREA] >= min_area:
            clean[label_map == lbl] = 255

    # ── Step 3: Skeleton-guided endpoint bridging ─────────────────────────────
    if gap_px > 0 and _DEPS_OK:
        clean = _bridge_endpoints(clean, prob_map, gap_px=gap_px,
                                  prob_threshold=threshold)

    # ── Step 4: Final min-area filter — clean bridging residuals ─────────────
    n_labels, label_map, stats, _ = cv2.connectedComponentsWithStats(
        clean, connectivity=8
    )
    final = np.zeros_like(clean)
    for lbl in range(1, n_labels):
        if stats[lbl, cv2.CC_STAT_AREA] >= 10:
            final[label_map == lbl] = 255

    return final   # (H, W) uint8  {0, 255}


# ─────────────────────────────────────────────────────────────────────────────
# Skeletonization
# ─────────────────────────────────────────────────────────────────────────────

def skeletonize_mask(binary_mask: np.ndarray) -> np.ndarray:
    """
    Produces a 1-pixel-wide medial-axis skeleton via scikit-image skeletonize.

    Args:
        binary_mask : (H, W) uint8 {0, 255}

    Returns:
        (H, W) bool  skeleton
    """
    if not _DEPS_OK:
        raise ImportError("scikit-image required for skeletonization.")
    return skeletonize((binary_mask > 0).astype(bool))


# ─────────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────────

def _get_neighbours(skel: np.ndarray, r: int, c: int):
    """Return 8-connected skeleton neighbour coordinates of (r, c)."""
    H, W = skel.shape
    nbrs = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < H and 0 <= nc < W and skel[nr, nc]:
                nbrs.append((nr, nc))
    return nbrs


def skeleton_to_graph(skeleton: np.ndarray) -> "nx.Graph":
    """
    Converts a binary skeleton to a NetworkX graph.

    Nodes  : junction pixels (degree ≥ 3) and endpoint pixels (degree = 1)
    Edges  : vessel segments connecting node pairs, weighted by path length

    Args:
        skeleton : (H, W) bool

    Returns:
        nx.Graph with node attributes 'pos', 'node_type'
                 and edge attribute 'length'
    """
    if not _DEPS_OK:
        raise ImportError("networkx required.")

    skel_pts   = np.argwhere(skeleton)
    degree_map = {
        tuple(pt): len(_get_neighbours(skeleton, *pt))
        for pt in skel_pts
    }
    nodes = {pt for pt, deg in degree_map.items() if deg == 1 or deg >= 3}

    G = nx.Graph()
    for n in nodes:
        G.add_node(n, pos=n,
                   node_type="junction" if degree_map[n] >= 3 else "endpoint")

    visited_edges = set()

    def trace_edge(start_node, start_pt):
        path   = [start_node, start_pt]
        prev, curr = start_node, start_pt
        length = np.linalg.norm(np.array(start_pt) - np.array(start_node))
        while curr not in nodes:
            nbrs = [nb for nb in _get_neighbours(skeleton, *curr) if nb != prev]
            if not nbrs:
                break
            nxt    = nbrs[0]
            length += np.linalg.norm(np.array(nxt) - np.array(curr))
            path.append(nxt)
            prev, curr = curr, nxt
        return (curr if curr in nodes else None), path, length

    for node in nodes:
        for nbr in _get_neighbours(skeleton, *node):
            key = tuple(sorted([node, nbr]))
            if key in visited_edges:
                continue
            visited_edges.add(key)
            if nbr in nodes:
                G.add_edge(node, nbr, length=1.0, path=[node, nbr])
            else:
                end_node, path, length = trace_edge(node, nbr)
                if end_node and end_node != node and not G.has_edge(node, end_node):
                    G.add_edge(node, end_node, length=length, path=path)

    return G


# ─────────────────────────────────────────────────────────────────────────────
# Combined pipeline
# ─────────────────────────────────────────────────────────────────────────────

def full_postprocess_pipeline(prob_map: np.ndarray,
                               threshold: float = 0.5,
                               gap_px:    int   = 7):
    """
    End-to-end post-processing for one probability map.

    Args:
        prob_map  : (H, W) float32 [0,1]
        threshold : vessel probability cutoff (default 0.5)
        gap_px    : max endpoint gap to bridge (default 7)

    Returns:
        refined_mask : (H, W) uint8  {0, 255}
        skeleton     : (H, W) bool
        graph        : nx.Graph  (or None if deps unavailable)
    """
    refined_mask = postprocess_mask(prob_map, threshold=threshold, gap_px=gap_px)

    skeleton = None
    graph    = None
    if _DEPS_OK:
        skeleton = skeletonize_mask(refined_mask)
        graph    = skeleton_to_graph(skeleton)

    return refined_mask, skeleton, graph


# ─────────────────────────────────────────────────────────────────────────────
# Visualisation
# ─────────────────────────────────────────────────────────────────────────────

def visualise_graph(original_rgb: np.ndarray,
                    refined_mask: np.ndarray,
                    skeleton: np.ndarray,
                    graph: "nx.Graph",
                    max_nodes: int = 600):
    """
    Plots: original fundus | post-processed mask | skeleton + graph overlay.
    """
    import matplotlib.patches as mpatches
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    axes[0].imshow(original_rgb)
    axes[0].set_title("Original fundus", fontsize=13)
    axes[0].axis("off")

    axes[1].imshow(refined_mask, cmap="gray")
    axes[1].set_title("Post-processed mask", fontsize=13)
    axes[1].axis("off")

    axes[2].imshow(original_rgb, alpha=0.35)
    if skeleton is not None:
        axes[2].imshow(skeleton, cmap="Blues", alpha=0.65)

    if graph is not None and _DEPS_OK:
        nodes_list = list(graph.nodes(data=True))[:max_nodes]
        for (r, c), attr in nodes_list:
            colour = "red" if attr.get("node_type") == "junction" else "yellow"
            axes[2].plot(c, r, "o", color=colour, markersize=3)

        for u, v, attr in list(graph.edges(data=True))[:max_nodes * 2]:
            path = attr.get("path", [u, v])
            axes[2].plot(
                [p[1] for p in path], [p[0] for p in path],
                "c-", linewidth=0.5, alpha=0.7
            )

        junctions = sum(1 for _, a in graph.nodes(data=True)
                        if a.get("node_type") == "junction")
        endpoints  = graph.number_of_nodes() - junctions
        axes[2].set_title(
            f"Skeleton + Graph\n"
            f"Nodes: {graph.number_of_nodes()}  "
            f"(J:{junctions} E:{endpoints})  "
            f"Edges: {graph.number_of_edges()}",
            fontsize=11
        )
    else:
        axes[2].set_title("Skeleton", fontsize=13)
    axes[2].axis("off")

    plt.tight_layout()
    plt.savefig("postprocess_graph.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("Saved → postprocess_graph.png")


print("Post-processing functions defined.")
print("Pipeline: single threshold → min-area filter → skeleton endpoint bridging")
print("  • NO dual threshold (prob_mean=0.12 makes low threshold unreliable)")
print("  • NO global morphological closing (causes blobs at vessel crossings)")
print("  • Endpoint bridging checks prob along gap — skips crossings automatically")
if not _DEPS_OK:
    print("[ACTION NEEDED]  !pip install scikit-image networkx")
