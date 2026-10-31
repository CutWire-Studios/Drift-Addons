#!/usr/bin/env python3
r"""Export the audio side of CLAP (laion/larger_clap_general) to ONNX and stage the audio tagging addon.

    uv run --python 3.12 --index-strategy unsafe-best-match \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        --with torch --with transformers --with onnx --with onnxruntime --with numpy --with safetensors \
        ./export-clap-audio.py

Needs torch (CPU build is enough), transformers, onnx, onnxruntime. Downloads the pinned checkpoint and
earshot's data files into ../staging/.cache (sha256-checked) and writes
../staging/audio-clap/models/audio-clap/:

  clap_audio.onnx        waveform -> 512-d unit embedding, front end included (see below)
  text_embeddings.bin    float32 [N, 512]: 49 event phrases, 322 vocabulary terms, the reference mean
  vocab.json             phrases, terms, calibration numbers, thresholds, section constants, row layout
  config.json            input / output contract Drift reads
  NOTICE.txt, LICENSE-Apache-2.0.txt

The graph
  input   waveform  float32 [batch, samples]   mono, 48 kHz, nominal range +-1
  output  embedding float32 [batch, 512]       L2-normalised, same space as text_embeddings.bin
The graph does what earshot's `_prep` plus the Hugging Face ClapFeatureExtractor ("repeatpad", slaney mel,
no fusion) do, so Drift only decodes, downmixes and resamples to 48 kHz mono. earshot's mono is ffmpeg's -ac 1 (each
stereo channel at -3 dB, summed: 0.707 * (L + R)) and its calibration was measured with that, so use the
same gain for correlated stereo. Per clip the graph does:
  1. keep the first 480000 samples (10 s), zero-pad up to 480 samples,
  2. tile the clip floor(480000 / n) times, zero-pad to 480000 (CLAP's training-time "repeatpad"),
  3. reflect-pad 512 each side, 1024-sample periodic Hann frames, hop 480 (1001 frames), |DFT|^2 as one
     strided Conv1d (the DFT basis is a constant), 64 slaney-scale / slaney-norm mel bands 50-14000 Hz,
     10*log10(max(x, 1e-10)),
  4. the HTSAT (Swin [2,2,12,2]) audio encoder, the two-layer audio projection, L2 normalisation.
Clips longer than 10 s are not windowed here: Drift cuts 10 s windows (hop 5 s) itself and averages the
unit embeddings, like earshot.

Weights are stored as fp16 and computed in fp32 (recipes/onnx_fp16.py explains why this is not a blanket
fp16 conversion). The text branch is not shipped: the vocabulary embeddings are precomputed here from the
fp32 PyTorch text tower.

Where the numbers come from
  - Model: laion/larger_clap_general at 16c8cc3 (Apache-2.0); upstream LAION-AI/CLAP is CC0-1.0.
  - The vocabulary, prompt templates, per-phrase background means, reference mean embedding and every
    threshold are earshot's (MIT, Copyright (c) 2026 Leon Lin), read from the pinned commit below; nothing is
    recomputed except the text embeddings, which are earshot's recipe (each term through every template,
    unit-normalise, average, unit-normalise) on the pinned fp32 text tower.
"""

import ast
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import onnx_fp16  # noqa: E402
import staging_hashes  # noqa: E402

CLAP_REPO = "laion/larger_clap_general"
CLAP_REVISION = "16c8cc3159a3c8a31e8ff5ef1f66b0d9ab3667db"
CLAP_FILES = {
    "config.json": "6268f76a067e3104bf9001e97d7dcc0fcfb16f3086cfb478ee72d95900d7fc1d",
    "merges.txt": "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5",
    "model.safetensors": "c3d0e564a97cb5eccea412f11d5c51c8a1ccceb80c51e3c6957bb5a796b423b6",
    "preprocessor_config.json": "9739f58296aa6f9ac18008fd0150fb2649bc554985fbde86d0a4041c882ac753",
    "special_tokens_map.json": "06e405a36dfe4b9604f484f6a1e619af1a7f7d09e34a8555eb0b77b66318067f",
    "tokenizer_config.json": "e2eb445cfdbf4711de620cbdf10478b0423950799e85652d9f28da47066ab86d",
    "tokenizer.json": "dc239041d98de27ffc3975473a1a23e3db4c937b23c138c38bbc66588bd247e5",
    "vocab.json": "ed19656ea1707df69134c4af35c8ceda2cc9860bf2c3495026153a133670ab5e",
}

EARSHOT_COMMIT = "591fa3e028032e6dce56620a20e932e35667e8d8"
EARSHOT_FILES = {
    "earshot/data/vocab.json": "6e5ccf7b7d718caa1b3f896ae776f8fabd1540d41dd504e9c6c608740b65852a",
    "earshot/data/vocab_stats.json": "a43adf61888fbc35162635c0c85a48b9ae5904b27c9eb8441a20f40a3e5eef6e",
    "earshot/timeline.py": "4b1d036af173c1539cf21b67a256a461a838673c68fd1a9d58bda8a4226b72e5",
    "earshot/match.py": "4e78dcf0160d12688eb6bd712609b8efa7a500f61186469a48e315635398e300",
    "LICENSE": "d9177365c7471d18ecd623ce7b8849e26ab8d7e7fea13e1fcbda62397ecb9db8",
}

APACHE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt"
APACHE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"

OPSET = 17
SAMPLE_RATE = 48000
WINDOW = 480000
MIN_SAMPLES = 480
N_FFT = 1024
HOP = 480
EMBED_DIM = 512


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


def fetch_checkpoint() -> Path:
    folder = CACHE / f"clap-{CLAP_REVISION[:8]}"
    for name, digest in CLAP_FILES.items():
        url = f"https://huggingface.co/{CLAP_REPO}/resolve/{CLAP_REVISION}/{name}"
        download(url, folder / name, digest)
    return folder


def fetch_earshot() -> Path:
    folder = CACHE / f"earshot-{EARSHOT_COMMIT[:8]}"
    for name, digest in EARSHOT_FILES.items():
        url = f"https://raw.githubusercontent.com/Leonxlnx/earshot/{EARSHOT_COMMIT}/{name}"
        download(url, folder / name, digest)
    return folder


def module_constants(source: str, wanted: set) -> dict:
    """Module-level literals of an earshot source file, read with ast so nothing is retyped."""
    found = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                found[target.id] = ast.literal_eval(node.value)
            elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple):
                for name, value in zip(target.elts, node.value.elts):
                    if isinstance(name, ast.Name) and name.id in wanted:
                        found[name.id] = ast.literal_eval(value)
    missing = wanted - found.keys()
    if missing:
        raise SystemExit(f"constants not found in earshot source: {sorted(missing)}")
    return found


def function_defaults(source: str, function: str) -> dict:
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == function:
            args = node.args.args[len(node.args.args) - len(node.args.defaults):]
            return {a.arg: ast.literal_eval(d) for a, d in zip(args, node.args.defaults)}
    raise SystemExit(f"function {function} not found in earshot source")


def build_audio_graph(model):
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers import ClapFeatureExtractor

    extractor = ClapFeatureExtractor.from_pretrained(str(CACHE / f"clap-{CLAP_REVISION[:8]}"))

    class FrontEnd(nn.Module):
        """ClapFeatureExtractor._np_extract_fbank_features for one 10 s clip, as tensor ops."""

        def __init__(self):
            super().__init__()
            n = np.arange(N_FFT)[:, None]
            k = np.arange(N_FFT // 2 + 1)[None, :]
            window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)  # periodic Hann
            angle = 2 * np.pi * n * k / N_FFT
            basis = np.concatenate([window[:, None] * np.cos(angle), -window[:, None] * np.sin(angle)], 1)
            self.register_buffer("dft", torch.tensor(basis.T[:, None, :], dtype=torch.float32))
            self.register_buffer("mel", torch.tensor(extractor.mel_filters_slaney, dtype=torch.float32))

        def forward(self, x):
            x = F.pad(x[:, None, :], (N_FFT // 2, N_FFT // 2), mode="reflect")
            y = F.conv1d(x, self.dft, stride=HOP)
            bins = N_FFT // 2 + 1
            power = (y[:, :bins] ** 2 + y[:, bins:] ** 2).transpose(1, 2)
            return 10.0 * torch.log10(torch.clamp(power @ self.mel, min=1e-10))

    class ClapAudio(nn.Module):
        def __init__(self, clap):
            super().__init__()
            self.frontend = FrontEnd()
            self.clap = clap

        def forward(self, waveform):
            x = waveform[:, :WINDOW]
            short = torch.maximum(torch.tensor(MIN_SAMPLES) - x.shape[1], torch.tensor(0))
            x = torch.cat([x, torch.zeros(x.shape[0], short, dtype=x.dtype)], 1)
            x = x.repeat(1, WINDOW // x.shape[1])
            x = torch.cat([x, torch.zeros(x.shape[0], WINDOW - x.shape[1], dtype=x.dtype)], 1)
            features = self.frontend(x)[:, None]
            return self.clap.get_audio_features(input_features=features).pooler_output

    return ClapAudio(model).eval()


def export_audio(model, out: Path) -> dict:
    import onnx
    import torch

    graph = build_audio_graph(model)
    example = torch.randn(2, 100000) * 0.1
    tmp = CACHE / "clap_audio_fp32.onnx"
    torch.onnx.export(
        graph,
        (example,),
        str(tmp),
        input_names=["waveform"],
        output_names=["embedding"],
        dynamic_axes={"waveform": {0: "batch", 1: "samples"}, "embedding": {0: "batch"}},
        opset_version=OPSET,
        dynamo=False,
    )
    proto = onnx.load(str(tmp))
    stats = onnx_fp16.store_weights_fp16(proto, keep=lambda name: name.startswith("frontend."))
    onnx.checker.check_model(proto)
    onnx.save(proto, str(out))
    tmp.unlink()
    print(f"fp16 weights: {stats}")
    return stats


def embed_texts(model, tokenizer_dir: Path, texts: list):
    import numpy as np
    import torch
    from transformers import ClapProcessor

    processor = ClapProcessor.from_pretrained(str(tokenizer_dir))
    rows = []
    for i in range(0, len(texts), 64):
        inputs = processor(text=texts[i:i + 64], return_tensors="pt", padding=True)
        with torch.inference_mode():
            e = model.get_text_features(**inputs)
        e = getattr(e, "pooler_output", e).float().numpy()
        rows.append(e / (np.linalg.norm(e, axis=1, keepdims=True) + 1e-12))
    return np.concatenate(rows)


def unit(a):
    import numpy as np

    return a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)


def build_vocab(model, clap_dir: Path, earshot: Path, out: Path) -> None:
    import numpy as np

    vocab = json.loads((earshot / "earshot/data/vocab.json").read_text(encoding="utf-8"))
    stats = json.loads((earshot / "earshot/data/vocab_stats.json").read_text(encoding="utf-8"))
    timeline_src = (earshot / "earshot/timeline.py").read_text(encoding="utf-8")
    match_src = (earshot / "earshot/match.py").read_text(encoding="utf-8")
    tl = module_constants(
        timeline_src,
        {"EVENT_VOCAB", "TAG_BG", "TAG_TEMPLATES", "TAG_CENTER", "EXPOSED_DB", "BURST_S", "NEAR_S", "SECTION_CATS",
         "Z_OK", "Z_WEAK", "NOVELTY_Z", "DETAIL", "AST_GENERIC"},
    )
    verdicts = module_constants(match_src, {"VERDICTS"})["VERDICTS"]
    section_defaults = function_defaults(timeline_src, "sections")

    templates = vocab["templates"]
    if list(tl["TAG_TEMPLATES"]) != templates:
        raise SystemExit("event and vocabulary templates differ; the shared embedding rows would be wrong")
    if stats["model"] != CLAP_REPO:
        raise SystemExit(f"earshot reference mean was measured with {stats['model']}")

    phrases = [(kind, text) for kind, texts in tl["EVENT_VOCAB"].items() for text in texts]
    terms = [(cat, text) for cat, texts in vocab["categories"].items() for text in texts]
    if set(tl["TAG_BG"]) != {t for _, t in phrases}:
        raise SystemExit("TAG_BG does not cover exactly the event phrases")

    names = [t for _, t in phrases] + [t for _, t in terms]
    texts = [template.format(name) for name in names for template in templates]
    per_template = embed_texts(model, clap_dir, texts).reshape(len(names), len(templates), EMBED_DIM)
    emb = unit(per_template.mean(axis=1)).astype(np.float32)
    mean_embedding = np.array(stats["mean"], dtype=np.float32)

    n_phrases = len(phrases)
    term_emb = emb[n_phrases:]
    bias = term_emb @ mean_embedding
    shipped = np.array([stats["term_cos"][t][0] for _, t in terms])
    drift = float(np.abs(bias - shipped).max())
    print(f"term bias recomputed vs earshot's vocab_stats term_cos: max |diff| {drift:.4f} "
          f"(earshot rounds to 4 places and measured with its own CLAP precision)")
    if drift > 0.01:
        raise SystemExit("recomputed text embeddings disagree with earshot's calibration; wrong tower or revision")

    rows = np.concatenate([emb, mean_embedding[None, :]]).astype(np.float32)
    (out / "text_embeddings.bin").write_bytes(rows.astype("<f4").tobytes())

    meta = {
        "format": 1,
        "model": {"repo": CLAP_REPO, "revision": CLAP_REVISION, "logit_scale": stats["logit_scale"]},
        "source": {
            "what": "vocabulary, templates, background means, reference mean embedding and thresholds are "
                    "earshot's data; only the text embeddings are computed here (fp32 PyTorch text tower)",
            "repo": "https://github.com/Leonxlnx/earshot",
            "commit": EARSHOT_COMMIT,
            "license": "MIT, Copyright (c) 2026 Leon Lin (see NOTICE.txt)",
            "files": EARSHOT_FILES,
            "reference_set": stats["reference_set"],
            "reference_recordings": stats["n_ref"],
            "reference_folders": stats["n_folders"],
            "reference_pad": stats["pad"],
            "reference_precision": stats["precision"],
        },
        "embeddings": {
            "file": "text_embeddings.bin",
            "dtype": "float32",
            "byte_order": "little-endian",
            "dim": EMBED_DIM,
            "rows": {
                "event_phrases": {"first": 0, "count": n_phrases},
                "vocab_terms": {"first": n_phrases, "count": len(terms)},
                "reference_mean": {"first": n_phrases + len(terms), "count": 1},
            },
            "note": "phrase and term rows are unit length (each term through every template, rows "
                    "unit-normalised, averaged, unit-normalised again); the reference mean row is the "
                    "folder-balanced mean of the audio embeddings of the reference recordings and is not "
                    "unit length",
        },
        "templates": templates,
        "event_phrases": [
            {"text": text, "kind": kind, "background_mean": tl["TAG_BG"][text]} for kind, text in phrases
        ],
        "vocab_terms": [
            {"text": text, "category": cat, "bias": round(float(b), 5)} for (cat, text), b in zip(terms, bias)
        ],
        "scoring": {
            "event_tags": "cos = A @ phrases.T; d = cos - event_tag_center * background_mean; "
                          "z = (d - mean_over_phrases(d)) / (std_over_phrases(d) + 1e-9); population std; "
                          "top 3 by z; kind of the best phrase is the event kind. A is the unit embedding of "
                          "the event excerpt (event start - 20 ms .. + clamp(length, 0.3 s, 1.5 s); swells "
                          "rise_ms before to 0.3 s after), repeat-padded to 10 s (done inside the graph)",
            "section_tags": "cos = A @ terms.T; z = (cos - mean_over_terms) / (std_over_terms + 1e-9); no bias "
                            "removal; top 2 per category in section_categories. A is the normalised mean of "
                            "the section's window embeddings",
            "calibrated_match": "u = cos - bias (bias = term . reference_mean); z = (u - mean_over_terms(u)) / "
                                "(std_over_terms(u) + 1e-9); verdict from verdict_thresholds_z. This is "
                                "earshot's match / describe / find / rank score. bias of any other query = "
                                "query . reference_mean",
        },
        "constants": {
            "event_tag_center": tl["TAG_CENTER"],
            "exposed_db": tl["EXPOSED_DB"],
            "burst_s": tl["BURST_S"],
            "near_s": tl["NEAR_S"],
            "verdict_thresholds_z": {name: threshold for threshold, name in verdicts},
            "section_categories": list(tl["SECTION_CATS"]),
            "z_ok": tl["Z_OK"],
            "z_weak": tl["Z_WEAK"],
            "section_merge_cos": section_defaults["merge_cos"],
            "section_min_len_s": section_defaults["min_len"],
            "section_ast_budget": section_defaults["ast_budget"],
            "section_novelty_z": tl["NOVELTY_Z"],
            "section_max_count": "max(2, ceil(duration_s / 8))",
            "detail_presets": tl["DETAIL"],
            "ast_generic_labels": sorted(tl["AST_GENERIC"]),
            "window_s": 10.0,
            "window_hop_s": 5.0,
            "unvalidated_categories": ["music_genre", "music_mood", "instruments", "voice"],
        },
    }
    (out / "vocab.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"vocab   {n_phrases} event phrases, {len(terms)} terms, {rows.shape[0]} rows")


def write_metadata(out: Path, earshot: Path, apache: Path) -> None:
    config = {
        "format": 1,
        "model": "clap_audio.onnx",
        "source": {"repo": CLAP_REPO, "revision": CLAP_REVISION, "weights": "model.safetensors",
                   "weights_sha256": CLAP_FILES["model.safetensors"]},
        "input": {
            "name": "waveform", "dtype": "float32", "shape": ["batch", "samples"],
            "sample_rate": SAMPLE_RATE, "channels": "mono, 0.707 * (L + R) for stereo (ffmpeg -ac 1, what earshot and its calibration used)",
            "range": "nominal +-1", "max_samples": WINDOW,
            "note": "samples beyond 480000 are ignored; shorter clips are zero-padded to 480 samples, then "
                    "repeat-padded to 10 s inside the graph. All items in a batch share one length",
        },
        "output": {"name": "embedding", "dtype": "float32", "shape": ["batch", EMBED_DIM], "normalised": True},
        "front_end_in_graph": True,
        "weights": "fp16 initializers, fp32 compute",
        "window_s": 10.0,
        "window_hop_s": 5.0,
        "window_reduce": "mean of unit embeddings, renormalised",
        "vocabulary": "vocab.json",
    }
    (out / "config.json").write_text(json.dumps(config, indent=1) + "\n")
    earshot_license = (earshot / "LICENSE").read_text(encoding="utf-8").strip()
    (out / "LICENSE-Apache-2.0.txt").write_bytes(apache.read_bytes())
    (out / "NOTICE.txt").write_text(
        f"""CLAP audio tagging

clap_audio.onnx is a converted derivative of the audio tower (HTSAT audio encoder and audio projection) of
laion/larger_clap_general, revision {CLAP_REVISION}
(https://huggingface.co/{CLAP_REPO}). The Hugging Face model card licenses that checkpoint under the
Apache-2.0 License (full text in LICENSE-Apache-2.0.txt). The upstream project, LAION-AI/CLAP
(https://github.com/LAION-AI/CLAP), is released under CC0-1.0.
The conversion changed the weights only by storing them in fp16; the mel front end and the 10 s repeat padding
were added to the graph so Drift can feed raw audio. Exported by recipes/export-clap-audio.py.

Training data: CLAP was trained on LAION-Audio-630K, AudioSet and music / speech sets. The weights licence
does not clear the licences of that training data.

text_embeddings.bin and vocab.json hold CLAP text embeddings of a fixed vocabulary, computed with the same
checkpoint, together with the vocabulary, prompt templates, per-phrase background means, reference mean
embedding and thresholds from earshot (https://github.com/Leonxlnx/earshot, commit {EARSHOT_COMMIT}),
used under the MIT License:

{earshot_license}
""",
        encoding="utf-8",
    )


def main() -> int:
    from transformers import ClapModel

    out = STAGING / "audio-clap" / "models" / "audio-clap"
    out.mkdir(parents=True, exist_ok=True)
    clap_dir = fetch_checkpoint()
    earshot = fetch_earshot()
    apache = download(APACHE_URL, CACHE / "apache-2.0.txt", APACHE_SHA256)

    model = ClapModel.from_pretrained(str(clap_dir)).eval()
    export_audio(model, out / "clap_audio.onnx")
    build_vocab(model, clap_dir, earshot, out)
    write_metadata(out, earshot, apache)

    staging_hashes.write_sidecars_under(STAGING / "audio-clap")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
