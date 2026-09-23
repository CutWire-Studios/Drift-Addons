#!/usr/bin/env python3
"""Stage the depth addon (Video Depth Anything, Small).

    ./fetch-vda.py            export and stage
    ./fetch-vda.py --verify   also check the ONNX graphs against PyTorch and time them on CPU

Unlike the other model recipes this one exports rather than downloads: ByteDance publishes only a
PyTorch checkpoint. The script clones the upstream repo and fetches the checkpoint, both pinned and
cached under ../staging/.cache, then exports two graphs:

    vda_small_encoder_*.onnx  DINOv2 ViT-S, one frame at a time: image [N,3,H,W] ->
                              feat1..feat4 [N,384,H/14,W/14]
    vda_small_head_*.onnx     the temporal DPT head, one 32-frame window at a time:
                              feat1..feat4 [32,384,H/14,W/14] -> disparity [1,32,H,W]

Upstream runs the whole window through one forward pass. Splitting it keeps the encoder's attention
to one frame (32 frames of ViT attention at 518x924 is several GB), and lets Drift reuse the
features of the ten frames each window carries over from the previous one instead of encoding them
twice. The windowing itself — which frames carry over, the scale/shift alignment and the seam blend
— is Drift's job (VdaDepth), and must follow upstream's infer_video_depth; constants.json carries
its numbers so the two cannot drift apart silently.

H and W must be multiples of 14. Output is relative inverse depth (disparity, larger = nearer), not
metres, and is not normalised per frame.

Needs: torch, torchvision, onnx, onnxscript, onnxconverter-common, onnxruntime, einops, easydict,
opencv-python-headless, numpy, tqdm. CPU builds of torch are enough.

Only the Small model is Apache-2.0. Base and Large are CC-BY-NC-4.0 and must not be staged here.
"""

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

# Pinned: an upstream change underneath us would silently change what ships.
REPO_URL = "https://github.com/DepthAnything/Video-Depth-Anything.git"
REPO_COMMIT = "4f5ae23172ba60fd7bc11ef671cca678842c7072"
REPO_DIR = CACHE / "Video-Depth-Anything"
CKPT_NAME = "video_depth_anything_vits.pth"
CKPT_URL = ("https://huggingface.co/depth-anything/Video-Depth-Anything-Small/resolve/"
            "256875362cff76724b920335dfb4b29dd611f66e/" + CKPT_NAME)
CKPT_SHA256 = "13379300b739e659f076a59d52e9801bd8d38c541a7e71f73bbca4dcfb013609"

PACKAGE = "vda-small"
ROOT = "models/depth"
PATCH = 14
WINDOW = 32
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]

# The contract with Drift's VdaDepth. "files" follows RvmMatter's convention: a precision only
# counts as installed when both of its graphs are on disk. fp16 is used only on a GPU provider.
CONSTANTS = {
    "model": "video_depth_anything_vits",
    "variant": "vda-small",
    "output": "disparity",
    "files": {
        "fp32": {"encoder": "vda_small_encoder_fp32.onnx", "head": "vda_small_head_fp32.onnx"},
        "fp16": {"encoder": "vda_small_encoder_fp16.onnx", "head": "vda_small_head_fp16.onnx"},
    },
    "window": WINDOW,
    # Upstream infer_video_depth: each window after the first starts with the previous window's
    # inputs at these indices, then continues with new frames.
    "overlap": 10,
    "keyframes": [0, 12, 24, 25, 26, 27, 28, 29, 30, 31],
    # Scale/shift is fitted on the first (overlap - interpLen) keyframes; the other interpLen
    # overlapping frames are cross-faded into the previous window's output.
    "interpLen": 8,
    "shortSide": 518,
    "multipleOf": PATCH,
    "mean": MEAN,
    "std": STD,
}

NOTICE = """Video Depth Anything
Copyright (2025) Bytedance Ltd. and/or its affiliates.
Licensed under the Apache License, Version 2.0.
Source: https://github.com/DepthAnything/Video-Depth-Anything

The bundled weights are the Small (ViT-S) relative-depth checkpoint, exported to ONNX by
drift-addons/recipes/fetch-vda.py from commit """ + REPO_COMMIT + """.
The motion module derives from AnimateDiff (Apache-2.0); the encoder is DINOv2 (Apache-2.0).
"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, expected: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256_of(dest) == expected:
        print(f"cached  {dest.name}")
        return dest
    print(f"fetch   {url}")
    urllib.request.urlretrieve(url, dest)
    actual = sha256_of(dest)
    if actual != expected:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"sha256 mismatch for {url}\n  expected {expected}\n  got      {actual}")
    return dest


def ensure_repo() -> None:
    if not REPO_DIR.exists():
        print(f"clone   {REPO_URL}")
        subprocess.run(["git", "clone", "-q", REPO_URL, str(REPO_DIR)], check=True)
    head = subprocess.run(["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    if head != REPO_COMMIT:
        subprocess.run(["git", "-C", str(REPO_DIR), "fetch", "-q", "origin"], check=True)
        subprocess.run(["git", "-C", str(REPO_DIR), "checkout", "-q", REPO_COMMIT], check=True)


def load_model(ckpt: Path):
    import torch

    sys.path.insert(0, str(REPO_DIR))
    from video_depth_anything.video_depth import VideoDepthAnything

    model = VideoDepthAnything(encoder="vits", features=64, out_channels=[48, 96, 192, 384])
    model.load_state_dict(torch.load(ckpt, map_location="cpu"), strict=True)
    return model.eval()


def make_exportable(model) -> None:
    """Swap DINOv2's position-embedding resize for one that stays symbolic in H and W.

    Upstream resizes by a float scale_factor ((H/14 + 0.1) / 37), which the exporter bakes into
    a constant. Resizing to an explicit size is the variant upstream left commented out; the
    coordinate mapping differs by the 0.1 offset, which --verify measures against the original.
    """
    import torch
    import torch.nn.functional as F

    backbone = model.pretrained

    def interpolate_pos_encoding(x, w, h):
        pos_embed = backbone.pos_embed.float()
        n = pos_embed.shape[1] - 1
        side = int(math.sqrt(n))
        dim = x.shape[-1]
        patch_pos_embed = F.interpolate(
            pos_embed[:, 1:].reshape(1, side, side, dim).permute(0, 3, 1, 2),
            size=(w // PATCH, h // PATCH),
            mode="bicubic",
            align_corners=False,
        )
        patch_pos_embed = patch_pos_embed.permute(0, 2, 3, 1).reshape(1, -1, dim)
        return torch.cat((pos_embed[:, :1], patch_pos_embed), dim=1).to(x.dtype)

    backbone.interpolate_pos_encoding = interpolate_pos_encoding

    # The head's final resize is to (int(patch_h * 14), int(patch_w * 14)); int() on a symbolic
    # size pins it to the example input, silently exporting the head for one resolution only.
    # sym_int keeps it symbolic and is the identity on plain ints.
    import video_depth_anything.dpt_temporal as dpt_temporal
    dpt_temporal.int = torch.sym_int


def wrappers(model):
    import torch
    import torch.nn.functional as F

    class Encoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = model.pretrained
            self.layers = model.intermediate_layer_idx["vits"]

        def forward(self, image):
            ph, pw = image.shape[2] // PATCH, image.shape[3] // PATCH
            feats = self.backbone.get_intermediate_layers(image, self.layers, return_class_token=True)
            return tuple(f[0].permute(0, 2, 1).reshape(f[0].shape[0], f[0].shape[2], ph, pw)
                         for f in feats)

    class Head(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.head = model.head

        def forward(self, feat1, feat2, feat3, feat4):
            ph, pw = feat1.shape[2], feat1.shape[3]
            tokens = [(f.flatten(2).permute(0, 2, 1),) for f in (feat1, feat2, feat3, feat4)]
            depth = self.head(tokens, ph, pw, WINDOW)[0]
            return F.relu(depth).reshape(1, WINDOW, ph * PATCH, pw * PATCH)

    return Encoder().eval(), Head().eval()


def export(model, out: Path) -> dict:
    import onnx
    import onnx.inliner
    import torch
    from onnxconverter_common import float16

    make_exportable(model)
    encoder, head = wrappers(model)
    feats = [f"feat{i}" for i in range(1, 5)]

    n = torch.export.Dim("n", min=1, max=64)
    ph = torch.export.Dim("ph", min=8, max=160)
    pw = torch.export.Dim("pw", min=8, max=160)
    # Deliberately not square and not 37x37, so neither the pos-embed shortcut nor a baked-in
    # 518x518 can hide in the graph.
    image = torch.randn(2, 3, 518, 924)
    with torch.no_grad():
        sample = encoder(image)

    paths = {}
    graphs = {
        "encoder": (encoder, (image,), ["image"], feats,
                    {"image": {0: n, 2: PATCH * ph, 3: PATCH * pw}}),
        "head": (head, tuple(torch.cat([f] * (WINDOW // 2)) for f in sample), feats, ["disparity"],
                 {name: {2: ph, 3: pw} for name in feats}),
    }
    for name, (module, args, inputs, outputs, dynamic) in graphs.items():
        fp32 = out / CONSTANTS["files"]["fp32"][name]
        print(f"export  {fp32.name}")
        with torch.no_grad():
            program = torch.onnx.export(module, args, dynamo=True, input_names=inputs,
                                        output_names=outputs, dynamic_shapes=dynamic,
                                        opset_version=18, external_data=False)
        program.optimize()
        program.save(str(fp32), external_data=False)
        proto = onnx.inliner.inline_local_functions(onnx.load(str(fp32)))
        # torch.onnx falls back to a fixed-shape export without failing when a guard pins a
        # dynamic dim, so check the graph really kept H and W symbolic.
        for value in proto.graph.input:
            if any(not d.dim_param for d in value.type.tensor_type.shape.dim[2:]):
                raise SystemExit(f"{fp32.name}: input {value.name} lost its dynamic H/W")
        onnx.save(proto, str(fp32))

        fp16 = out / CONSTANTS["files"]["fp16"][name]
        print(f"convert {fp16.name}")
        onnx.save(float16.convert_float_to_float16(proto, keep_io_types=True), str(fp16))
        paths[name] = (fp32, fp16)
    return paths


def verify(model_original, paths: dict) -> None:
    import numpy as np
    import onnxruntime as ort
    import torch

    def session(path):
        opts = ort.SessionOptions()
        return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])

    def window(h, w):
        # A smooth scene with a drifting bright blob, so the head sees temporal structure.
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        frames = []
        for t in range(WINDOW):
            cx, cy = w * (0.3 + 0.01 * t), h * 0.5
            blob = np.exp(-(((xs - cx) ** 2 + (ys - cy) ** 2) / (0.02 * w * w)))
            rgb = np.stack([ys / h, xs / w, blob], axis=0)
            frames.append((rgb - np.array(MEAN)[:, None, None]) / np.array(STD)[:, None, None])
        return np.stack(frames).astype(np.float32)

    @torch.no_grad()
    def reference(x):
        # Upstream forward() with the encoder run a frame at a time: frames only meet in the head,
        # and batching all 32 through ViT attention at 518x924 takes several GB.
        layers = model_original.intermediate_layer_idx["vits"]
        per_frame = [model_original.pretrained.get_intermediate_layers(x[t:t + 1], layers,
                                                                      return_class_token=True)
                     for t in range(WINDOW)]
        feats = [(torch.cat([f[i][0] for f in per_frame]),) for i in range(4)]
        h, w = x.shape[2], x.shape[3]
        depth = model_original.head(feats, h // PATCH, w // PATCH, WINDOW)[0]
        return torch.relu(depth).reshape(1, WINDOW, h, w).numpy()

    for index, precision in enumerate(("fp32", "fp16")):
        enc = session(paths["encoder"][index])
        hd = session(paths["head"][index])
        for h, w in ((392, 700), (518, 924)):
            x = window(h, w)
            ref = reference(torch.from_numpy(x))

            start = time.perf_counter()
            feats = [[] for _ in range(4)]
            for t in range(WINDOW):
                for i, f in enumerate(enc.run(None, {"image": x[t:t + 1]})):
                    feats[i].append(f)
            encoded = time.perf_counter()
            got = hd.run(None, {f"feat{i + 1}": np.concatenate(feats[i]) for i in range(4)})[0]
            done = time.perf_counter()

            span = float(ref.max() - ref.min()) or 1.0
            err = np.abs(got - ref)
            print(f"verify  {precision} {h}x{w}: max err {err.max() / span:.2e}, "
                  f"mean err {err.mean() / span:.2e} (of range {span:.3g}); CPU encoder "
                  f"{(encoded - start) * 1000 / WINDOW:.0f} ms/frame, head "
                  f"{(done - encoded) * 1000:.0f} ms/window")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true",
                        help="compare the exported graphs with PyTorch and time them on CPU")
    args = parser.parse_args()

    ensure_repo()
    ckpt = download(CKPT_URL, CACHE / CKPT_NAME, CKPT_SHA256)

    out = STAGING / PACKAGE / ROOT
    out.mkdir(parents=True, exist_ok=True)
    paths = export(load_model(ckpt), out)
    (out / "constants.json").write_text(json.dumps(CONSTANTS, indent=1) + "\n")
    (out / "NOTICE.txt").write_text(NOTICE)
    staging_hashes.write_sidecars_under(STAGING / PACKAGE)
    print(f"staged  {out}")

    if args.verify:
        verify(load_model(ckpt), paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
