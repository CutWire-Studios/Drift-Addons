#!/usr/bin/env python3
r"""Export the Audio Spectrogram Transformer (AudioSet) to ONNX and stage the speech / music detection addon.

    uv run --python 3.12 --index-strategy unsafe-best-match \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        --with torch --with transformers --with onnx --with onnxruntime --with numpy --with safetensors \
        ./export-ast.py

Downloads the pinned checkpoint and the earshot constants into ../staging/.cache (sha256-checked) and
writes ../staging/audio-ast/models/audio-ast/:

  ast_audioset.onnx     waveform -> 527 AudioSet logits and probabilities, front end included
  labels.json           the 527 AudioSet label names, in output order
  config.json           input / output contract, label indices Drift needs, earshot's thresholds
  NOTICE.txt, LICENSE-BSD-3-Clause.txt

The graph
  input   waveform      float32 [batch, samples]   mono, 16 kHz, nominal range +-1
  outputs logits        float32 [batch, 527]
          probabilities float32 [batch, 527]       sigmoid(logits), AudioSet is multi-label
The Kaldi-style filterbank front end of ASTFeatureExtractor is inside the graph:
  1. zero-pad to at least 1600 samples (earshot's floor),
  2. 400-sample frames, hop 160, no centring, no edge padding: n = (samples - 400) // 160 + 1 frames,
  3. per frame: subtract the mean, pre-emphasis 0.97 (x[i] - 0.97 x[i-1], x[0] * 0.03), symmetric
     (non-periodic) Hann window, 512-point DFT, power. All of that is linear, so it is one strided Conv1d whose
     kernel is built from the numpy reference operations applied to the identity,
  4. 128 Kaldi mel bands 20-8000 Hz triangular in mel space (ASTFeatureExtractor's table, a constant),
     ln(max(x, 1.1920929e-07)),
  5. the frame axis is zero-padded (after the log) or truncated to 1024, then (x + 4.2677393) / (2 * 4.5689974).
The model sees 1024 x 128 = 10.24 s. Longer audio: Drift cuts 10.24 s windows with a 5.12 s hop (the last one
aligned to the end), as earshot does, and reduces the probabilities by max (events) or mean (sections).

Weights are stored as fp16 and computed in fp32 (recipes/onnx_fp16.py explains why).

Sources
  - MIT/ast-finetuned-audioset-10-10-0.4593 at f826b80 (BSD-3-Clause, Copyright (c) 2021 Yuan Gong,
    https://github.com/YuanGongND/ast).
  - The speech / music thresholds in config.json are earshot's (MIT, Copyright (c) 2026 Leon Lin), read from the
    pinned commit below.
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

AST_REPO = "MIT/ast-finetuned-audioset-10-10-0.4593"
AST_REVISION = "f826b80d28226b62986cc218e5cec390b1096902"
AST_FILES = {
    "config.json": "a93d525511d77e8ecc933d09674b85099815bbbb417c228a4edd655e252fb9ff",
    "model.safetensors": "ae0c1e2ad4e1381d851fa9bf298ba13ebc9c5a914cdee2dbe427a6583869924d",
    "preprocessor_config.json": "8d04ba5a9c6fca5d39d0de2b1fd05ecf79deb589fbba279728bbebac39934231",
}

EARSHOT_COMMIT = "591fa3e028032e6dce56620a20e932e35667e8d8"
EARSHOT_FILES = {
    "earshot/timeline.py": "4b1d036af173c1539cf21b67a256a461a838673c68fd1a9d58bda8a4226b72e5",
    "LICENSE": "d9177365c7471d18ecd623ce7b8849e26ab8d7e7fea13e1fcbda62397ecb9db8",
}

BSD_3_CLAUSE = """BSD 3-Clause License

Copyright (c) 2021, Yuan Gong
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

OPSET = 17
SAMPLE_RATE = 16000
FRAME = 400
HOP = 160
FFT = 512
MIN_SAMPLES = 1600
MAX_FRAMES = 1024
MEL_BINS = 128
MEL_FLOOR = 1.192092955078125e-07
PREEMPHASIS = 0.97
MEAN = -4.2677393
STD = 4.5689974
WINDOW_S = 10.24


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
    folder = CACHE / f"ast-{AST_REVISION[:8]}"
    for name, digest in AST_FILES.items():
        download(f"https://huggingface.co/{AST_REPO}/resolve/{AST_REVISION}/{name}", folder / name, digest)
    return folder


def fetch_earshot() -> Path:
    folder = CACHE / f"earshot-{EARSHOT_COMMIT[:8]}"
    for name, digest in EARSHOT_FILES.items():
        download(
            f"https://raw.githubusercontent.com/Leonxlnx/earshot/{EARSHOT_COMMIT}/{name}", folder / name, digest
        )
    return folder


def module_constants(source: str, wanted: set) -> dict:
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    found[target.id] = ast.literal_eval(node.value)
    missing = wanted - found.keys()
    if missing:
        raise SystemExit(f"constants not found in earshot source: {sorted(missing)}")
    return found


def build_graph(model, extractor):
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers.audio_utils import window_function

    window = window_function(FRAME, "hann", periodic=False)

    def reference_frame(frame):
        """The per-frame steps of transformers.audio_utils.spectrogram, up to the DFT."""
        buffer = np.zeros(FFT)
        buffer[:FRAME] = frame - frame.mean()
        buffer[1:FRAME] -= PREEMPHASIS * buffer[:FRAME - 1]
        buffer[0] *= 1 - PREEMPHASIS
        buffer[:FRAME] *= window
        return np.fft.rfft(buffer)

    # The map frame -> DFT is linear: build its matrix by feeding the identity.
    spectra = np.stack([reference_frame(row) for row in np.eye(FRAME)])  # [400, 257] complex
    kernel = np.concatenate([spectra.real, spectra.imag], axis=1).T[:, None, :]  # [514, 1, 400]
    bins = FFT // 2 + 1

    class FrontEnd(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer("dft", torch.tensor(kernel, dtype=torch.float32))
            self.register_buffer("mel", torch.tensor(extractor.mel_filters, dtype=torch.float32))  # [257, 128]

        def forward(self, x):
            y = F.conv1d(x[:, None, :], self.dft, stride=HOP)
            power = (y[:, :bins] ** 2 + y[:, bins:] ** 2).transpose(1, 2)
            fbank = torch.log(torch.clamp(power @ self.mel, min=MEL_FLOOR))
            short = torch.maximum(torch.tensor(MAX_FRAMES) - fbank.shape[1], torch.tensor(0))
            fbank = torch.cat([fbank, torch.zeros(fbank.shape[0], short, MEL_BINS, dtype=fbank.dtype)], 1)
            return (fbank[:, :MAX_FRAMES] - MEAN) / (STD * 2)

    class AstAudio(nn.Module):
        def __init__(self, ast_model):
            super().__init__()
            self.frontend = FrontEnd()
            self.ast = ast_model

        def forward(self, waveform):
            short = torch.maximum(torch.tensor(MIN_SAMPLES) - waveform.shape[1], torch.tensor(0))
            x = torch.cat([waveform, torch.zeros(waveform.shape[0], short, dtype=waveform.dtype)], 1)
            logits = self.ast(input_values=self.frontend(x)).logits
            return logits, torch.sigmoid(logits)

    return AstAudio(model).eval()


def export(model, extractor, out: Path) -> None:
    import onnx
    import torch

    graph = build_graph(model, extractor)
    example = torch.randn(2, 40000) * 0.1
    tmp = CACHE / "ast_audioset_fp32.onnx"
    torch.onnx.export(
        graph,
        (example,),
        str(tmp),
        input_names=["waveform"],
        output_names=["logits", "probabilities"],
        dynamic_axes={
            "waveform": {0: "batch", 1: "samples"},
            "logits": {0: "batch"},
            "probabilities": {0: "batch"},
        },
        opset_version=OPSET,
        dynamo=False,
    )
    proto = onnx.load(str(tmp))
    stats = onnx_fp16.store_weights_fp16(proto, keep=lambda name: name.startswith("frontend."))
    onnx.checker.check_model(proto)
    onnx.save(proto, str(out))
    tmp.unlink()
    print(f"fp16 weights: {stats}")


def write_metadata(out: Path, model, earshot: Path) -> None:
    labels = [model.config.id2label[i] for i in range(len(model.config.id2label))]
    index = {name: labels.index(name) for name in ("Speech", "Music", "Silence")}
    tl = module_constants((earshot / "earshot/timeline.py").read_text(encoding="utf-8"), {"AST_GENERIC"})
    (out / "labels.json").write_text(json.dumps(labels, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    config = {
        "format": 1,
        "model": "ast_audioset.onnx",
        "source": {"repo": AST_REPO, "revision": AST_REVISION, "weights": "model.safetensors",
                   "weights_sha256": AST_FILES["model.safetensors"]},
        "input": {
            "name": "waveform", "dtype": "float32", "shape": ["batch", "samples"],
            "sample_rate": SAMPLE_RATE, "channels": "mono, 0.707 * (L + R) for stereo (ffmpeg -ac 1, as earshot)",
            "resample": "from 48 kHz with soxr HQ in earshot; any good resampler",
            "range": "nominal +-1",
            "note": "at least 1600 samples are used (shorter input is zero-padded); frames beyond 1024 "
                    "(163840 samples = 10.24 s) are ignored. All items in a batch share one length",
        },
        "outputs": [
            {"name": "logits", "dtype": "float32", "shape": ["batch", len(labels)]},
            {"name": "probabilities", "dtype": "float32", "shape": ["batch", len(labels)],
             "note": "sigmoid(logits), independent per class"},
        ],
        "front_end_in_graph": True,
        "weights": "fp16 initializers, fp32 compute",
        "window_s": WINDOW_S,
        "window_hop_s": WINDOW_S / 2,
        "window_alignment": "starts 0, hop, ...; one extra window aligned to the end when the tail is left over",
        "window_reduce": {"events": "max over windows", "sections": "mean over windows"},
        "labels": "labels.json",
        "label_index": index,
        "earshot": {
            "commit": EARSHOT_COMMIT,
            "license": "MIT, Copyright (c) 2026 Leon Lin (see NOTICE.txt)",
            "event_voice_threshold": {"label": "Speech", "min_probability": 0.5,
                                      "meaning": "an event whose AST Speech probability is >= 0.5 is a VOICE"},
            "event_top_labels": {"count": 4, "min_probability": 0.05},
            "section_music_threshold": {"label": "Music", "min_probability": 0.3},
            "section_speech_threshold": {"label": "Speech", "min_probability": 0.3},
            "section_presence_labels": ["Music", "Speech", "Silence"],
            "section_top_labels": {"count": 5, "min_probability": 0.05},
            "section_extra_source_min_probability": 0.08,
            "section_extra_sources_max": 3,
            "section_extra_sources_exclude": sorted(tl["AST_GENERIC"]),
            "section_crop_s": WINDOW_S,
        },
    }
    (out / "config.json").write_text(json.dumps(config, indent=1) + "\n")
    (out / "LICENSE-BSD-3-Clause.txt").write_text(BSD_3_CLAUSE)
    earshot_license = (earshot / "LICENSE").read_text(encoding="utf-8").strip()
    (out / "NOTICE.txt").write_text(
        f"""Audio Spectrogram Transformer (speech / music detection)

ast_audioset.onnx is a converted derivative of {AST_REPO}, revision {AST_REVISION}
(https://huggingface.co/{AST_REPO}), the AST of Gong, Chung and Glass fine-tuned on AudioSet
(https://github.com/YuanGongND/ast), released under the BSD 3-Clause License (full text in
LICENSE-BSD-3-Clause.txt; Copyright (c) 2021 Yuan Gong). The conversion changed the weights only by storing
them in fp16; the Kaldi-style filterbank front end was added to the graph so Drift can feed raw audio.
Exported by recipes/export-ast.py.

The model was initialised from an ImageNet-pretrained DeiT and trained on AudioSet; the weights licence does
not clear the licences of that training data.

The probability thresholds in config.json come from earshot (https://github.com/Leonxlnx/earshot, commit
{EARSHOT_COMMIT}), used under the MIT License:

{earshot_license}
""",
        encoding="utf-8",
    )


def main() -> int:
    from transformers import ASTFeatureExtractor, ASTForAudioClassification

    out = STAGING / "audio-ast" / "models" / "audio-ast"
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = fetch_checkpoint()
    earshot = fetch_earshot()

    model = ASTForAudioClassification.from_pretrained(str(checkpoint), attn_implementation="eager").eval()
    extractor = ASTFeatureExtractor.from_pretrained(str(checkpoint))
    if not hasattr(extractor, "mel_filters"):
        raise SystemExit("torchaudio is installed, so the extractor has no numpy mel table; run without it")
    export(model, extractor, out / "ast_audioset.onnx")
    write_metadata(out, model, earshot)

    staging_hashes.write_sidecars_under(STAGING / "audio-ast")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
