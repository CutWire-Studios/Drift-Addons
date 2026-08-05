# Drift Addons

Official addons for [Drift](https://github.com/CutWire-Studios/Drift), the free and open-source
video editor.

Addons are optional content packs — fonts, effects, transitions, stickers, AI models — that Drift
downloads on demand instead of bundling. Keeping them out of the app means a small download to get
started, and new effects can ship without a new release. You install them from **Extra packs** in
Drift's settings; there is nothing to download by hand.

This repository holds the source content for those packs and the tooling that builds, signs and
publishes them.

## What's available

| Addon | What it adds |
| --- | --- |
| Essential Video Effects | Colour fixes, blurs, glow, glitch, green screen, warps, beauty and makeup |
| Trending Effects | Ready-made looks and effect templates |
| Essential Transitions | Fades, wipes, slides and other shot-to-shot transitions |
| Essential Audio Effects | Reverb, EQ, pitch and voice shaping |
| Essential Fonts | 21 font families for titles and captions |
| Emoji Stickers | Emoji sticker set and the emoji font used for text |
| Auto Captions | Whisper speech-to-text model for automatic subtitles |
| Subject Cutout | SAM 2 model for isolating a subject from the background |
| Funny Face Effects | Face landmark model for face warps and makeup |
| Noise Removal | DeepFilterNet 3 model for cleaning up background noise |
| AI Engine | ONNX Runtime, in CPU, NVIDIA and general-GPU builds |

## How it works

An addon is a `.driftpkg`: a manifest, a table of contents, and every file's bytes in one
compressed frame. Each package is signed with an Ed25519 key whose public half is compiled into
Drift, and **Drift verifies that signature before it installs anything**. A package the key did not
sign cannot be installed, no matter where it came from.

Drift asks a small Cloudflare Worker for the catalogue, gets a short-lived download link per addon,
fetches the package, verifies it, and only then moves it into place. Published packages are
immutable — a new release is a new version, never a rewrite — so a download that succeeded once
keeps working.

## Repository layout

```
recipes/    one recipe per addon, plus the scripts that assemble their content
packer/     builds, signs and publishes .driftpkg archives
worker/     the Cloudflare Worker that serves the catalogue
staging/    assembled addon trees, ready to pack
assets/     shared inputs, such as the base image used for effect thumbnails
```

Large model weights and native libraries are not in git — a checksum sits beside each one and the
bytes are synced separately. Everything else, including fonts, shaders and package metadata, is
here in full.

## Building a package

Content is assembled into `staging/`, packed into a signed archive, then published:

```bash
python3 recipes/stage.py fonts effects transitions
python3 packer/pack.py recipes/fonts-essentials.json
python3 packer/publish.py dist/fonts.essentials-1.0.0.driftpkg
```

`stage.py` takes any of `fonts`, `stickers`, `whisper`, `sam2`, `face`, `effects`,
`effects-trending`, `transitions`, `audio-effects`, `denoise`, and defaults to all of them.
Packing needs the `zstd` and `openssl` command-line tools; publishing needs an authenticated
`wrangler`. To cut a new release, bump `version` in the recipe and run the same two commands.

Some effects and transitions exist only as addons rather than in the app. Those are generated with
`recipes/generate-content-packages.py`, and their thumbnails with `recipes/generate-thumbs.py`.

## The AI engine addons

Drift does not link ONNX Runtime. It loads whichever build you installed at runtime, so the choice
between a CPU build and a GPU-accelerated one stays yours, and the app stays small for everyone who
never touches the AI features.

Two kinds ship from here:

- **A runtime** — a complete ONNX Runtime, one per platform, in a CPU or NVIDIA/CUDA build.
- **An execution provider** — a plugin that layers onto whichever runtime you already have. WebGPU
  is the one available, and it is how AMD and Intel graphics get accelerated without downloading a
  second 200 MB runtime.

These are the only packages tied to a specific platform, and Drift will not offer or install one
built for a different one. They are fetched from upstream rather than assembled locally:

```bash
python3 recipes/fetch-onnxruntime.py                     # everything upstream publishes
python3 recipes/fetch-onnxruntime.py cpu:linux-x64       # or one at a time
```

The script writes the recipes too. Upgrading ONNX Runtime means editing one version table at the
top of it and re-running, rather than hand-editing a dozen near-identical files.

There is no ROCm build — upstream removed it in 1.23 — and no OpenVINO, which ships only as a
Python wheel.

## The Worker

The catalogue is served by a Cloudflare Worker sitting in front of an R2 bucket. It exposes the
index and hands out expiring download links; the app retries against a fresh index if a link has
aged out. Responses are cached at the edge, so common downloads cost nothing to serve.

```bash
cd worker && bun run deploy
```

## Licensing

The tooling in this repository, and the shaders and effect content written for it, are GPL-3.0 —
see [LICENSE](LICENSE).

Bundled third-party content is **not** covered by that and keeps its own terms. Each pack declares
its own in the `license` field of its recipe: the models are MIT or Apache-2.0, the fonts are
OFL-1.1 / UFL-1.0, and the HarmonyOS Sans emoji font is proprietary, redistributed under the terms
its publisher grants. Check the matching recipe before reusing anything from a pack.
