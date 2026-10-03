#!/usr/bin/env python3
"""Stage the video restore addon: every upscaler and the clean-up model, in one package.

    uv run --with onnx --with numpy ./fetch-restore.py

Downloads community single-image restoration models already exported to ONNX, converts the
half-precision ones to fp32, and writes the constants Drift reads beside them. Files are cached
under ../staging/.cache. Needs: onnx, numpy (for the fp16 -> fp32 conversion only).

One package, kind "restore-model", with a "models" array in constants.json. Each entry carries
what the picker shows: the content it is made for, a one-line summary, a before/after thumbnail
and its CPU time per megapixel of input.

fp32 throughout: on the CPU provider the fp16 exports ran 1.5-1.7x slower than their fp32
conversions (ONNX Runtime casts around every op it has no fp16 kernel for), and differed from them
by under 0.001.

Thumbnails and speeds come from restore-bench/ (bench.py, thumbgen.py), measured on an Intel Core
i5-12450H with ONNX Runtime 1.27 on 12 threads, 512 px tiles with Drift's 16 px context. Rerun
those and update SPEED if a model changes. Speeds are seconds per megapixel of *input*.

Sources:
  - Thanawanit/Upscale on Hugging Face bundles Adore, Ani4K v2, Balanced, LiveAction V1, the
    Real-ESRGAN compact pair and the Strong series as Model.zip. Its README lists Balanced and the
    Strong series as of unknown origin and license; they ship on the user's decision.
  - 4x-ClearRealityV1 is only published as a .pth on Mega; the ONNX export is pinned by hash and
    must be placed in ../staging/.cache by hand.
  - Nomos8k's ONNX is only on Google Drive, so its URL is a Drive file id.
"""

import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"
BENCH = CACHE / "restore-bench"
PACKAGE = "restore-models"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

PHHOFM = "https://github.com/Phhofm/models/releases/download"
THANAWANIT_ZIP = (
    "https://huggingface.co/Thanawanit/Upscale/resolve/main/Model.zip",
    "91765c7f92ca934a11cdc72659dbbef994a8f367c7d57dd739af71ef22b5421d",
    "Thanawanit-Upscale-Model.zip",
)

# Pinned: a release asset that changed underneath us would silently change what ships.
DOWNLOADS = {
    "1xgaterv3_r_restore_fp32_op17_onnxslim.onnx": (
        f"{PHHOFM}/1xgaterv3_r_restore/1xgaterv3_r_restore_fp32_op17_onnxslim.onnx",
        "170d41231bfecc25dfe0db1cb3bf7b8080ac29fd173c872f517d12cf86416dd2",
    ),
    "2xNomosUni_span_multijpg_fp32_opset17.onnx": (
        f"{PHHOFM}/2xNomosUni_span_multijpg/2xNomosUni_span_multijpg_fp32_opset17.onnx",
        "4c088922fcb40584a95a1b98009e3042a61ada46f237a9e72e8a2ed127832004",
    ),
    "4xNomosUni_span_multijpg_fp32_opset17.onnx": (
        f"{PHHOFM}/4xNomosUni_span_multijpg/4xNomosUni_span_multijpg_fp32_opset17.onnx",
        "a435b009109e72c50ce95927dab0a6dde63e594cf57ba5a18ba63da67355698a",
    ),
    "4xNomos8k_span_otf_strong_fp32_opset17.onnx": (
        "https://drive.usercontent.google.com/download?id=1pbmnNdBrko12sudBVJSwNi1vg65bt1Af"
        "&export=download&confirm=t",
        "387f61730a99776f9a760770903ea2db4aa8b12f6bce1fa6f45a732f9151e3e9",
    ),
    "2x_OpenProteus_Compact_i2_70K_fp32.onnx": (
        "https://github.com/Sirosky/Upscale-Hub/releases/download/OpenProteus/"
        "2x_OpenProteus_Compact_i2_70K_fp32.onnx",
        "133688b581809213d6a792c69aae5c6ce7d10aef859e593599d64d5974d25623",
    ),
}

# Members of Model.zip.
FROM_ZIP = {
    "Adore_2x.onnx": "f3e9dba612a83bfbb57a0fa7aaeb7e111e46753cab277eed2a942300d5ed15e0",
    "Ani4Kv2_2x.onnx": "747163e8572650380b0b2f16f89e8c3ce2c29cd19525e9af8782d4bf1fe653c2",
    "Balanced_2x.onnx": "3ad7a70077fd28f5457a323ba943d148a28b76cba80fd1881b3214c685affc9c",
    "LiveActionV1_2x.onnx": "bfa72f3c6347076aed140d0836cee30c27ea434c047beeaf9466469483836ecc",
    "RealESRGAN_2x.onnx": "91962dcc8bce51ce7e490b347a5fdae96e509b3d74d95999137ad641312b5f06",
    "RealESRGAN_4x.onnx": "3b55a4d0ce37e1812d5306911890cd0b1f174a4adcb7bdd4ed6a6f6318b14be1",
    "Strong_v1.5.onnx": "4da01f17d10231a47030f50e90abe4451d0cff3e1f0742e04922b835dad6518f",
    "Strong_v2.5.onnx": "8ef79e2cce05037f297784a6c648906da4f819e6728473bb4bb34d87e99b6c15",
    "Strong_v3.onnx": "ce5a1febde79d15e61cdb6bbb9785b02a11e494bbd7f87ec19c5528318410493",
}

# Placed in CACHE by hand.
LOCAL = {
    "4x-ClearRealityV1.onnx": "48b3d2c862e8325fab5041e6eaca6c307acb5ce11c9e683ea1b0796c17600595",
}

CC_BY = "Creative Commons Attribution 4.0 International (CC BY 4.0)\nhttps://creativecommons.org/licenses/by/4.0/"
CC_BY_NC = (
    "Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)\n"
    "https://creativecommons.org/licenses/by-nc/4.0/"
)
CC_BY_NC_SA = (
    "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)\n"
    "https://creativecommons.org/licenses/by-nc-sa/4.0/\n"
    "Converted from fp16 to fp32 for this package where noted; otherwise unmodified."
)
BSD3 = "BSD 3-Clause License\nhttps://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE"
UNKNOWN = (
    "Original author and license unknown. Redistributed from the Thanawanit/Upscale collection\n"
    "on Hugging Face, which itself lists the origin as unknown."
)

# id: (source file, packaged file, convert, constants entry, notice). Speeds from restore-bench.
MODELS = [
    ("1xGaterV3", "1xgaterv3_r_restore_fp32_op17_onnxslim.onnx", "1xGaterV3.onnx", False,
     {"name": "GaterV3", "task": "decompress", "scale": 1, "content": ["general"],
      "summary": "Cleans up compression, noise and mild blur without changing the size.",
      "secondsPerMegapixel": 8.35},
     f"1xgaterv3_r_restore by Philip Hofmann (Helaman), GaterV3 architecture (MIT)\n"
     f"Source: https://github.com/Phhofm/models/releases/tag/1xgaterv3_r_restore\n{CC_BY}"),
    ("2xBalanced", "Balanced_2x.onnx", "2xBalanced.onnx", True,
     {"name": "Balanced", "task": "upscale", "scale": 2, "content": ["anime"],
      "summary": "The fastest anime upscaler. Clean, slightly bolder lines.",
      "secondsPerMegapixel": 2.01},
     f"Balanced_2x (UltraCompact)\n{UNKNOWN}"),
    ("2xAdore", "Adore_2x.onnx", "2xAdore.onnx", True,
     {"name": "Adore", "task": "upscale", "scale": 2, "content": ["anime"],
      "summary": "Clears blur and sharpens line art in anime. Very fast.",
      "secondsPerMegapixel": 2.06},
     f"Adore by renarchi, UpCunet2x_fast architecture\n"
     f"Source: https://github.com/renarchi/Re-SISR\n{CC_BY_NC_SA}\nConverted from fp16 to fp32."),
    ("2xAni4Kv2", "Ani4Kv2_2x.onnx", "2xAni4Kv2.onnx", False,
     {"name": "Ani4K v2", "task": "upscale", "scale": 2, "content": ["anime", "cg"],
      "summary": "Natural anime upscales that keep soft backgrounds and depth of field.",
      "secondsPerMegapixel": 3.68},
     f"Ani4K v2 (Compact) by Sirosky\n"
     f"Source: https://github.com/Sirosky/Upscale-Hub\n{CC_BY_NC}"),
    ("2xStrong_v1.5", "Strong_v1.5.onnx", "2xStrong_v1.5.onnx", True,
     {"name": "Strong v1.5", "task": "upscale", "scale": 2, "content": ["anime"],
      "summary": "Removes compression and noise from anime while keeping a natural look.",
      "secondsPerMegapixel": 4.58},
     f"Strong_v1.5 (Compact)\n{UNKNOWN}"),
    ("2xStrong_v2.5", "Strong_v2.5.onnx", "2xStrong_v2.5.onnx", True,
     {"name": "Strong v2.5", "task": "upscale", "scale": 2, "content": ["anime"],
      "summary": "Smooths anime and draws bold, dark lines.",
      "secondsPerMegapixel": 4.51},
     f"Strong_v2.5 (Compact)\n{UNKNOWN}"),
    ("2xStrong_v3", "Strong_v3.onnx", "2xStrong_v3.onnx", True,
     {"name": "Strong v3", "task": "upscale", "scale": 2, "content": ["anime"],
      "summary": "The heaviest anime clean-up: flat colour and crisp, thick lines. Makes real faces look painted.",
      "secondsPerMegapixel": 4.50},
     f"Strong_v3 (Compact)\n{UNKNOWN}"),
    ("2xRealESRGAN-AnimeVideo", "RealESRGAN_2x.onnx", "2xRealESRGAN-AnimeVideo.onnx", True,
     {"name": "Real-ESRGAN Anime Video", "task": "upscale", "scale": 2, "content": ["anime"],
      "summary": "Smooth, clean anime with bold edges.",
      "secondsPerMegapixel": 4.44},
     f"realesr-animevideov3 (2x, SRVGGNetCompact) by Xintao Wang\n"
     f"Source: https://github.com/xinntao/Real-ESRGAN\n{BSD3}\nConverted from fp16 to fp32."),
    ("2xLiveActionV1", "LiveActionV1_2x.onnx", "2xLiveActionV1.onnx", False,
     {"name": "LiveAction V1", "task": "upscale", "scale": 2, "content": ["live", "cg"],
      "summary": "Made for live-action video: faces, skin and film footage.",
      "secondsPerMegapixel": 3.25},
     f"2xLiveActionV1_SPAN (490000 iterations) by jcj83429\n"
     f"Source: https://openmodeldb.info/models/2x-LiveActionV1-SPAN\n{CC_BY_NC_SA}"),
    ("2xNomosUni", "2xNomosUni_span_multijpg_fp32_opset17.onnx", "2xNomosUni.onnx", False,
     {"name": "NomosUni", "task": "upscale", "scale": 2, "content": ["live", "general"],
      "summary": "General photo and video upscaler that copes with JPEG compression.",
      "secondsPerMegapixel": 3.23},
     f"2xNomosUni_span_multijpg by Philip Hofmann (Helaman)\n"
     f"Source: https://github.com/Phhofm/models/releases/tag/2xNomosUni_span_multijpg\n{CC_BY}"),
    ("2xOpenProteus", "2x_OpenProteus_Compact_i2_70K_fp32.onnx", "2xOpenProteus.onnx", False,
     {"name": "OpenProteus", "task": "upscale", "scale": 2, "content": ["live", "cg"],
      "summary": "Natural detail for clean HD live action and 3D renders.",
      "secondsPerMegapixel": 4.29},
     f"Open Proteus (2x_OpenProteus_Compact_i2_70K) by Sirosky\n"
     f"Source: https://github.com/Sirosky/Upscale-Hub/releases/tag/OpenProteus\n{CC_BY_NC}"),
    ("4xClearReality", "4x-ClearRealityV1.onnx", "4xClearReality.onnx", False,
     {"name": "ClearReality V1", "task": "upscale", "scale": 4, "content": ["live"],
      "summary": "Soft, natural 4x for real footage. Good on faces, hair and nature.",
      "secondsPerMegapixel": 3.19},
     f"4x-ClearRealityV1 by Kim2091, SPAN architecture\n"
     f"Source: https://openmodeldb.info/models/4x-ClearRealityV1\n{CC_BY_NC_SA}"),
    ("4xNomosUni", "4xNomosUni_span_multijpg_fp32_opset17.onnx", "4xNomosUni.onnx", False,
     {"name": "NomosUni", "task": "upscale", "scale": 4, "content": ["live", "general"],
      "summary": "General photo and video upscaler that copes with JPEG compression.",
      "secondsPerMegapixel": 3.33},
     f"4xNomosUni_span_multijpg by Philip Hofmann (Helaman)\n"
     f"Source: https://github.com/Phhofm/models/releases/tag/4xNomosUni_span_multijpg\n{CC_BY}"),
    ("4xNomos8kStrong", "4xNomos8k_span_otf_strong_fp32_opset17.onnx", "4xNomos8kStrong.onnx", False,
     {"name": "Nomos8k Strong", "task": "upscale", "scale": 4, "content": ["live"],
      "summary": "For badly degraded footage: removes heavy blur, noise and compression.",
      "secondsPerMegapixel": 3.31},
     f"4xNomos8k_span_otf_strong by Philip Hofmann (Helaman)\n"
     f"Source: https://openmodeldb.info/models/4x-Nomos8k-span-otf-strong\n{CC_BY}"),
    ("4xRealESRGAN-General", "RealESRGAN_4x.onnx", "4xRealESRGAN-General.onnx", True,
     {"name": "Real-ESRGAN General", "task": "upscale", "scale": 4, "content": ["general", "anime"],
      "summary": "Smooth and clean on most content. The slowest upscaler here.",
      "secondsPerMegapixel": 8.98},
     f"realesr-general-x4v3 (SRVGGNetCompact) by Xintao Wang\n"
     f"Source: https://github.com/xinntao/Real-ESRGAN\n{BSD3}\nWeights converted from fp16 to fp32."),
]


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


def to_fp32(src: Path, dest: Path) -> None:
    """Rewrites every fp16 tensor, type and cast in the graph as fp32."""
    import numpy as np
    import onnx
    from onnx import AttributeProto, TensorProto, numpy_helper

    f16, f32 = TensorProto.FLOAT16, TensorProto.FLOAT

    def fix_tensor(t):
        if t.data_type == f16:
            t.CopyFrom(numpy_helper.from_array(numpy_helper.to_array(t).astype(np.float32), t.name))

    def fix_graph(g):
        for t in g.initializer:
            fix_tensor(t)
        for v in list(g.input) + list(g.output) + list(g.value_info):
            if v.type.HasField("tensor_type") and v.type.tensor_type.elem_type == f16:
                v.type.tensor_type.elem_type = f32
        for node in g.node:
            for a in node.attribute:
                if a.type == AttributeProto.TENSOR:
                    fix_tensor(a.t)
                elif a.type == AttributeProto.TENSORS:
                    for t in a.tensors:
                        fix_tensor(t)
                elif a.type == AttributeProto.GRAPH:
                    fix_graph(a.g)
                elif a.type == AttributeProto.GRAPHS:
                    for sg in a.graphs:
                        fix_graph(sg)
                elif a.name in ("to", "dtype") and a.type == AttributeProto.INT and a.i == f16:
                    a.i = f32

    model = onnx.load(str(src))
    fix_graph(model.graph)
    # Shape info written for the fp16 graph would still claim fp16; drop it and infer again.
    del model.graph.value_info[:]
    model = onnx.shape_inference.infer_shapes(model)
    onnx.checker.check_model(model)
    onnx.save(model, str(dest))


def main() -> int:
    for name, (url, digest) in DOWNLOADS.items():
        download(url, CACHE / name, digest)

    url, digest, zip_name = THANAWANIT_ZIP
    archive = download(url, CACHE / zip_name, digest)
    with zipfile.ZipFile(archive) as z:
        for name, expected in FROM_ZIP.items():
            dest = CACHE / f"thanawanit-{name}"
            if not dest.exists() or sha256_of(dest) != expected:
                dest.write_bytes(z.read(f"Model/{name}"))
            if sha256_of(dest) != expected:
                raise SystemExit(f"sha256 mismatch for {name} in {zip_name}")

    for name, expected in LOCAL.items():
        path = CACHE / name
        if not path.exists() or sha256_of(path) != expected:
            raise SystemExit(f"{path} is missing or changed; it is not downloadable, copy it in by hand")

    out = STAGING / PACKAGE / "models" / "restore" / PACKAGE
    if out.exists():
        for old in out.rglob("*"):
            if old.is_file():
                old.unlink()
    (out / "thumbs").mkdir(parents=True, exist_ok=True)

    entries = []
    notices = []
    for model_id, source, packaged, convert, constants, notice in MODELS:
        src = CACHE / (f"thanawanit-{source}" if source in FROM_ZIP else source)
        if convert:
            to_fp32(src, out / packaged)
        else:
            (out / packaged).write_bytes(src.read_bytes())
        thumb = BENCH / "thumbs" / f"{model_id}.jpg"
        if not thumb.exists():
            raise SystemExit(f"{thumb} is missing; run restore-bench/thumbgen.py first")
        (out / "thumbs" / thumb.name).write_bytes(thumb.read_bytes())
        entries.append({"model": model_id, **constants, "files": {"fp32": packaged},
                        "thumbnail": f"thumbs/{thumb.name}"})
        notices.append(f"{packaged}\n{notice}\n")
        print(f"staged  {packaged}")

    (out / "constants.json").write_text(json.dumps({"models": entries}, indent=1) + "\n")
    (out / "NOTICE.txt").write_text(
        "Thumbnails show frames from Tears of Steel (c) Blender Foundation | mango.blender.org, CC BY 3.0,\n"
        "and Pepper&Carrot by David Revoy, www.peppercarrot.com, CC BY 4.0.\n\n" + "\n".join(notices))
    staging_hashes.write_sidecars_under(STAGING / PACKAGE)
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
