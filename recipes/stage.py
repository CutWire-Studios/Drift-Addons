#!/usr/bin/env python3
"""Stage each addon's content into ../staging/<name>/ ready for the packer.

    ./stage.py fonts stickers whisper

Each staged directory becomes the package root, so `provides[].root` in the matching recipe
names a subdirectory of it. Sources are the local asset directories that used to be bundled
into the Drift build tree. Fonts, images, JSON, and shaders under staging/ are committed;
large weights/libs stay gitignored with a sibling `.sha256` sidecar (see staging_hashes.py).
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
STAGING = ROOT / "staging"
CONTENT = ROOT / "content"
DRIFT = Path.home() / "Projects" / "VideoEd"

import staging_hashes  # noqa: E402

TRENDING_EFFECT_IDS = [
    "bling_sparkle",
    "star_filter",
    "light_leak",
    "lens_flare",
    "halation",
    "bokeh_dream",
    "beat_shake",
    "zoom_pulse",
    "spin_blur",
    "strobe_flash",
    "motion_trail",
    "halftone_comic",
    "sketch_pencil",
    "oil_paint",
    "duotone",
    "super8_film",
    "cinematic_grade",
    "kaleidoscope",
    "wave_warp",
    "droste_zoom",
    "lightning_sky",
]


def _reset(name: str) -> Path:
    target = STAGING / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    return target


def stage_fonts(source: Path) -> Path:
    """fonts/<family>/{family.json, *.ttf, OFL.txt} — exactly what FontCatalog scans."""
    target = _reset("fonts-essentials")
    families = sorted(p for p in source.iterdir() if (p / "family.json").is_file())
    if not families:
        sys.exit(f"no font families under {source} — run recipes/fetch-fonts.py first")
    for family in families:
        shutil.copytree(family, target / "fonts" / family.name)
    print(f"fonts: {len(families)} families")
    return target


def stage_stickers(font: Path) -> Path:
    """Extract the emoji PNGs, then convert stickers.json into the pack.json StickerCatalog wants.

    The extractor predates the addon system and still writes the old flat manifest, so the shape
    conversion happens here rather than forking the script.

    The font itself rides along under emoji-font/. The extracted PNGs are a curated ~170 of the
    ~1900 emoji it can draw, and the app's emoji picker rasterises the rest on demand — which it
    can only do with the face that produced the stickers, so the two ship together rather than as
    a second download that is useless on its own.
    """
    target = _reset("stickers-harmonyos")
    pack_dir = target / "stickers" / "harmonyos"
    pack_dir.mkdir(parents=True)

    subprocess.run(
        [sys.executable, str(HERE / "extract-stickers.py"),
         "--font", str(font), "--out", str(pack_dir), "--force"],
        check=True,
    )

    manifest = json.loads((pack_dir / "stickers.json").read_text())
    if not manifest.get("stickers"):
        sys.exit(f"no stickers extracted from {font}")

    (pack_dir / "pack.json").write_text(json.dumps({
        "id": "harmonyos",
        "name": "HarmonyOS Emoji",
        "license": "Proprietary — HarmonyOS Sans",
        "order": 0,
        "categories": manifest.get("categories", []),
        "stickers": manifest["stickers"],
    }, indent=2))
    (pack_dir / "stickers.json").unlink()

    font_dir = target / "emoji-font"
    font_dir.mkdir()
    shutil.copy2(font, font_dir / font.name)

    size = font.stat().st_size
    print(f"stickers: {len(manifest['stickers'])} emoji + {font.name} ({size / 1e6:.0f} MB)")
    return target


def stage_packages(name: str, kind: str, source: Path) -> Path:
    """effects/<id>/ and transitions/<id>/ — copied verbatim from the app repo.

    Unlike the other addons these ship with the build too, as the baseline every install starts
    with. The addon exists so an updated shader can be pushed without an app release; installed
    packages take priority over the bundled copy of the same id.
    """
    target = _reset(name)
    packages = sorted(p for p in source.iterdir()
                      if p.is_dir() and (p / f"{kind[:-1]}.json").is_file())
    if not packages:
        sys.exit(f"no {kind} packages under {source}")
    for package in packages:
        shutil.copytree(package, target / kind / package.name)
    print(f"{kind}: {len(packages)} packages")
    return target


def stage_packages_allowlist(name: str, kind: str, manifest: str, source: Path,
                             ids: list[str]) -> int:
    """Copy only the listed package ids — lets core and trending packs share one source tree."""
    copied = 0
    for package_id in ids:
        package = source / package_id
        if not (package / manifest).is_file():
            sys.exit(f"missing {kind} package '{package_id}' under {source}")
        shutil.copytree(package, STAGING / name / kind / package_id)
        copied += 1
    print(f"{kind}: {copied} packages (allowlist)")
    return copied


def _ensure_content_packages() -> None:
    """Regenerate addon-only shaders under content/ if that tree is empty."""
    effects = CONTENT / "effects"
    transitions = CONTENT / "transitions"
    need = (not effects.is_dir() or not any(effects.iterdir())
            or not transitions.is_dir() or not any(transitions.iterdir()))
    if need:
        subprocess.run([sys.executable, str(HERE / "generate-content-packages.py")], check=True)


def _merge_content_packages(staged_root: Path, kind: str) -> int:
    """Copy addon-local packages from content/<kind>/ into a staged core tree."""
    source = CONTENT / kind
    if not source.is_dir():
        return 0
    manifest = f"{kind[:-1]}.json"
    merged = 0
    for package in sorted(p for p in source.iterdir()
                          if p.is_dir() and (p / manifest).is_file()):
        dest = staged_root / kind / package.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(package, dest)
        merged += 1
    # Ships with the package: the ported gl-transitions shaders are MIT, and their per-file
    # Author/License headers plus this index are the attribution that has to travel with them.
    attribution = source / "ATTRIBUTION.md"
    if attribution.is_file():
        shutil.copy2(attribution, staged_root / kind / "ATTRIBUTION.md")
    if merged:
        print(f"{kind}: +{merged} from content/{kind}")
    return merged


def stage_effects_core(effects_dir: Path) -> Path:
    """Core GPU effects — VideoEd tree (minus trending) plus addon-only content/effects."""
    _ensure_content_packages()
    target = _reset("effects-core")
    trending = set(TRENDING_EFFECT_IDS)
    packages = sorted(
        p for p in effects_dir.iterdir()
        if p.is_dir() and (p / "effect.json").is_file() and p.name not in trending
    )
    if not packages:
        sys.exit(f"no effects packages under {effects_dir}")
    for package in packages:
        shutil.copytree(package, target / "effects" / package.name)
    extra = _merge_content_packages(target, "effects")
    print(f"effects: {len(packages) + extra} packages")
    return target


def stage_effects_trending(effects_dir: Path, templates_dir: Path) -> Path:
    """Trending GPU effects plus beat-synced templates in one staged tree."""
    target = _reset("effects-trending")
    stage_packages_allowlist("effects-trending", "effects", "effect.json", effects_dir,
                             TRENDING_EFFECT_IDS)
    template_count = 0
    for package in sorted(templates_dir.iterdir()):
        if package.is_dir() and (package / "template.json").is_file():
            shutil.copytree(package, target / "effect-templates" / package.name)
            template_count += 1
    if template_count == 0:
        sys.exit(f"no effect-templates under {templates_dir}")
    print(f"effect-templates: {template_count} packages")
    return target


def stage_whisper(source: Path) -> Path:
    """models/whisper-small/… — resolveWhisperModelDir() looks for encoder_model_fp16.onnx here."""
    target = _reset("whisper-small")
    if not (source / "encoder_model_fp16.onnx").is_file():
        sys.exit(f"no whisper model under {source}")
    shutil.copytree(source, target / "models" / "whisper-small")
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"whisper: {size / 1e6:.0f} MB")
    return target


def stage_sam2(source: Path) -> Path:
    """models/sam2/… — resolveSam2ModelDir() wants constants.json plus all five graphs.

    The graphs may sit flat or under onnx/; graphDir() accepts either, so the source layout is
    copied verbatim rather than normalised.
    """
    target = _reset("sam2-tiny")
    graphs = source / "onnx" if (source / "onnx").is_dir() else source
    required = ["vision_encoder.onnx", "mask_decoder.onnx", "memory_encoder.onnx",
                "memory_attention.onnx", "pointer_tpos.onnx"]
    missing = [f for f in required if not (graphs / f).is_file()]
    if not (source / "constants.json").is_file():
        missing.append("constants.json")
    if missing:
        sys.exit(f"incomplete sam2 model under {source}: missing {', '.join(missing)}")
    shutil.copytree(source, target / "models" / "sam2")
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"sam2: {size / 1e6:.0f} MB")
    return target


def stage_face(source: Path) -> Path:
    """models/face/… — resolveFaceModelDir() wants constants.json plus both graphs.

    Two upstream models under two different licences, so their terms travel with the weights
    rather than living only in the recipe's metadata: MediaPipe's face mesh is Apache-2.0 and
    needs its licence retained, YuNet is MIT and needs its copyright notice kept.
    """
    target = _reset("face-landmark")
    required = ["constants.json", "face_detector.onnx", "face_landmark.onnx"]
    missing = [f for f in required if not (source / f).is_file()]
    if missing:
        sys.exit(f"incomplete face model under {source}: missing {', '.join(missing)}")

    model_dir = target / "models" / "face"
    shutil.copytree(source, model_dir)

    licences = {
        "LICENSE.mediapipe.txt":
            "https://raw.githubusercontent.com/google/mediapipe/master/LICENSE",
        "LICENSE.yunet.txt":
            "https://raw.githubusercontent.com/opencv/opencv_zoo/main/"
            "models/face_detection_yunet/LICENSE",
    }
    for name, url in licences.items():
        subprocess.run(["curl", "-sSfL", url, "-o", str(model_dir / name)], check=True)

    (model_dir / "NOTICE.txt").write_text(
        "Drift face model addon\n"
        "\n"
        "face_landmark.onnx\n"
        "  MediaPipe face_landmark_with_attention (468 mesh points + iris refinement).\n"
        "  Source: https://github.com/google/mediapipe/tree/master/mediapipe/modules/face_landmark\n"
        "  ONNX export: https://github.com/PINTO0309/PINTO_model_zoo/tree/main/"
        "282_face_landmark_with_attention\n"
        "  Copyright The MediaPipe Authors. Apache-2.0 — see LICENSE.mediapipe.txt\n"
        "\n"
        "face_detector.onnx\n"
        "  YuNet face detector (face_detection_yunet_2023mar).\n"
        "  Source: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet\n"
        "  Copyright (c) 2020 Shiqi Yu. MIT — see LICENSE.yunet.txt\n"
    )

    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"face: {size / 1e6:.1f} MB")
    return target


def stage_denoise(source: Path) -> Path:
    """models/deepfilternet3/… — resolveModelDir() in DeepFilterDenoiser wants all three files.

    The auxiliary blob carries the ERB matrices and Vorbis window the DSP is built around, and
    config.json is checked against the constants compiled into the app, so a package missing
    either would install and then refuse to load.
    """
    target = _reset("deepfilternet3")
    required = ["deepfilter.onnx", "deepfilter-auxiliary.bin", "config.json"]
    missing = [f for f in required if not (source / f).is_file()]
    if missing:
        sys.exit(f"incomplete DeepFilterNet3 model under {source}: missing {', '.join(missing)}")
    shutil.copytree(source, target / "models" / "deepfilternet3")
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"denoise: {size / 1e6:.1f} MB")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    all_targets = ["fonts", "stickers", "whisper", "sam2", "face", "effects", "effects-trending",
                   "transitions", "audio-effects", "denoise"]
    parser.add_argument("targets", nargs="*", default=all_targets, choices=all_targets)
    parser.add_argument("--fonts-dir", type=Path, default=DRIFT / "fonts")
    parser.add_argument("--emoji-font", type=Path,
                        default=Path.home() / "Downloads" / "emojis" / "HarmonyOS_4.0.ttf")
    parser.add_argument("--whisper-dir", type=Path, default=DRIFT / "models" / "whisper-small")
    parser.add_argument("--sam2-dir", type=Path, default=DRIFT / "models" / "sam2")
    parser.add_argument("--face-dir", type=Path, default=DRIFT / "models" / "face")
    parser.add_argument("--effects-dir", type=Path, default=DRIFT / "effects")
    parser.add_argument("--templates-dir", type=Path, default=DRIFT / "effect-templates")
    parser.add_argument("--transitions-dir", type=Path, default=DRIFT / "transitions")
    parser.add_argument("--audio-effects-dir", type=Path, default=DRIFT / "audio-effects")
    parser.add_argument("--denoise-dir", type=Path, default=DRIFT / "models" / "deepfilternet3")
    args = parser.parse_args()

    if "fonts" in args.targets:
        stage_fonts(args.fonts_dir)
    if "stickers" in args.targets:
        stage_stickers(args.emoji_font)
    if "whisper" in args.targets:
        stage_whisper(args.whisper_dir)
    if "sam2" in args.targets:
        stage_sam2(args.sam2_dir)
    if "face" in args.targets:
        stage_face(args.face_dir)
    if "effects" in args.targets:
        stage_effects_core(args.effects_dir)
    if "effects-trending" in args.targets:
        stage_effects_trending(args.effects_dir, args.templates_dir)
    if "transitions" in args.targets:
        _ensure_content_packages()
        staged = stage_packages("transitions-core", "transitions", args.transitions_dir)
        _merge_content_packages(staged, "transitions")
    if "audio-effects" in args.targets:
        stage_packages("audio-effects-core", "audio-effects", args.audio_effects_dir)
    if "denoise" in args.targets:
        stage_denoise(args.denoise_dir)

    print("sha256 sidecars:")
    staging_hashes.write_sidecars_under(STAGING)


if __name__ == "__main__":
    main()
