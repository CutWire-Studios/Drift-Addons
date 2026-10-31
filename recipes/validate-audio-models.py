#!/usr/bin/env python3
r"""Check the staged CLAP and AST addons against earshot's PyTorch pipeline and write reference data.

    ./validate-audio-models.py --earshot ~/Projects/earshot-research/repo \
        --earshot-home ~/Projects/earshot-research/cache \
        --samples ~/Projects/earshot-research/samples \
        --refdata ~/Projects/earshot-research/refdata

Run it with the venv that has torch, transformers and onnxruntime, and with -I. Needs the staged addons
(export-clap-audio.py, export-ast.py). earshot is imported from its clone and run in fp32; nothing is written
to the clone (EARSHOT_HOME points elsewhere).

For every case it compares the staged ONNX model to earshot's PyTorch model and the staged vocabulary to
earshot's own, then writes the C++ port's reference data:
  <case>.wav48k.f32      the mono 48 kHz input (little-endian float32), CLAP graph input
  <case>.wav16k.f32      the 16 kHz input (earshot's soxr resample), AST graph input
  <case>.clap_mel.f32    ClapFeatureExtractor output [1,1,1001,64], the tensor inside the CLAP graph after the
                         front end (only for 10 s or shorter inputs after repeat padding)
  <case>.clap_embedding.f32  [512], earshot PyTorch fp32, unit length
  <case>.ast_fbank.f32   [1,1024,128], ASTFeatureExtractor output, the tensor inside the AST graph
  <case>.ast_logits.f32  [527]
  <case>.ast_probs.f32   [527]
  index.json             shapes, sources, tolerances and earshot's tag / z-score / label outputs
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CLAP_DIR = STAGING / "audio-clap" / "models" / "audio-clap"
AST_DIR = STAGING / "audio-ast" / "models" / "audio-ast"

SR48 = 48000
SR16 = 16000
CLAP_WINDOW = 10 * SR48
CLAP_HOP = 5 * SR48
AST_WINDOW = 163840  # 10.24 s at 16 kHz
AST_HOP = AST_WINDOW // 2


def clap_windows(x):
    """earshot.audio.windows(x, 10, 5, pad_last=True) for audio longer than 10 s, else the clip itself."""
    if len(x) <= CLAP_WINDOW:
        return [x]
    starts = list(range(0, len(x) - CLAP_WINDOW + 1, CLAP_HOP))
    if (len(x) - CLAP_WINDOW) % CLAP_HOP:
        starts.append(len(x) - CLAP_WINDOW)
    return [x[s:s + CLAP_WINDOW] for s in starts]


def ast_windows(y):
    if len(y) <= AST_WINDOW:
        return [y]
    starts = list(range(0, len(y) - AST_WINDOW + 1, AST_HOP))
    if (len(y) - AST_WINDOW) % AST_HOP:
        starts.append(len(y) - AST_WINDOW)
    return [y[s:s + AST_WINDOW] for s in starts]


def unit(v):
    import numpy as np

    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def pop_std(a):
    import numpy as np

    return a.std(axis=-1, keepdims=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--earshot", required=True)
    ap.add_argument("--earshot-home", required=True)
    ap.add_argument("--samples", required=True)
    ap.add_argument("--refdata", required=True)
    args = ap.parse_args()

    os.environ["EARSHOT_HOME"] = str(Path(args.earshot_home).resolve())
    os.environ["EARSHOT_PRECISION"] = "fp32"
    os.environ["EARSHOT_OFFLINE"] = "1"
    sys.path.insert(0, str(Path(args.earshot).resolve()))

    import numpy as np
    import onnxruntime as ort
    import soundfile as sf
    from earshot import audio, timeline, vocab
    from earshot.models import ast as east
    from earshot.models import clap as eclap

    refdir = Path(args.refdata)
    refdir.mkdir(parents=True, exist_ok=True)

    opts = ort.SessionOptions()
    clap_sess = ort.InferenceSession(str(CLAP_DIR / "clap_audio.onnx"), opts, providers=["CPUExecutionProvider"])
    ast_sess = ort.InferenceSession(str(AST_DIR / "ast_audioset.onnx"), opts, providers=["CPUExecutionProvider"])

    vocab_meta = json.loads((CLAP_DIR / "vocab.json").read_text(encoding="utf-8"))
    rows = np.fromfile(CLAP_DIR / "text_embeddings.bin", dtype="<f4").reshape(-1, 512)
    layout = vocab_meta["embeddings"]["rows"]
    phr = layout["event_phrases"]
    trm = layout["vocab_terms"]
    E_events = rows[phr["first"]:phr["first"] + phr["count"]]
    E_terms = rows[trm["first"]:trm["first"] + trm["count"]]
    ref_mean = rows[layout["reference_mean"]["first"]]
    phrase_names = [p["text"] for p in vocab_meta["event_phrases"]]
    phrase_kinds = [p["kind"] for p in vocab_meta["event_phrases"]]
    background = np.array([p["background_mean"] for p in vocab_meta["event_phrases"]])
    term_names = [t["text"] for t in vocab_meta["vocab_terms"]]
    term_cats = [t["category"] for t in vocab_meta["vocab_terms"]]
    term_bias = np.array([t["bias"] for t in vocab_meta["vocab_terms"]])
    consts = vocab_meta["constants"]
    labels = json.loads((AST_DIR / "labels.json").read_text(encoding="utf-8"))
    ast_cfg = json.loads((AST_DIR / "config.json").read_text())
    ast_idx = ast_cfg["label_index"]

    c = eclap.get()
    a = east.get()
    assert c.precision == "fp32" and a.precision == "fp32", (c.precision, a.precision)

    # ---- vocabulary rows against earshot's own embedding of the same texts
    et, ek, E_es = timeline._event_matrix(c)
    assert et == phrase_names and list(ek) == phrase_kinds, "event phrase order differs"
    ev = vocab.get()
    assert ev.names == term_names, "vocab term order differs"
    ev_cos = (E_es * E_events).sum(1)
    tm_cos = (ev.E * E_terms).sum(1)
    print(f"text rows vs earshot's (fp32 here): min cosine events {ev_cos.min():.6f}, terms {tm_cos.min():.6f}")
    print(f"reference mean vs earshot's vocab_stats: identical = {np.array_equal(ref_mean, ev.m)}")
    print(f"term bias vs earshot mu_E: max |diff| {np.abs(term_bias - ev.mu_E).max():.5f}")

    # ---- cases
    rng = np.random.default_rng(7)
    samples = {n: sf.read(Path(args.samples) / f"{n}.wav", dtype="float32")[0] for n in ("bursts", "film_audio", "sweep")}
    film, bursts, sweep = samples["film_audio"], samples["bursts"], samples["sweep"]
    onset = int(np.argmax(np.abs(np.diff(np.abs(bursts)))))  # sharpest jump: a burst edge
    cases = {
        "sweep_full": sweep,
        "film_full": film,
        "bursts_full": bursts,
        "film_window_0_10s": film[:CLAP_WINDOW],
        "bursts_event_0p5s": bursts[max(0, onset - 960):max(0, onset - 960) + 24000],
    }
    for i in range(5):
        n = int(rng.uniform(0.15, 9.0) * SR48)
        src = samples[("bursts", "film_audio", "sweep")[i % 3]]
        s = int(rng.integers(0, len(src) - n))
        cases[f"random_excerpt_{i}"] = src[s:s + n].copy()
    cases["film_quiet_minus60dB"] = film[:5 * SR48] * 1e-3
    cases["noise_3s"] = (rng.standard_normal(3 * SR48) * 0.05).astype(np.float32)
    cases["tiny_100_samples"] = (rng.standard_normal(100) * 0.1).astype(np.float32)

    report = {"cases": {}}
    worst_clap = 1.0
    worst_ast = 0.0
    tags_same = 0
    tags_total = 0
    clap_ms = []
    ast_ms = []
    for name, x in cases.items():
        x = np.asarray(x, np.float32)
        ref = c.embed_audio([x], pad="repeatpad")[0]
        t = time.perf_counter()
        parts = [clap_sess.run(None, {"waveform": w[None]})[0][0] for w in clap_windows(x)]
        clap_ms.append((time.perf_counter() - t) * 1000 / len(parts))
        ours = unit(np.mean(parts, axis=0))
        cos_clap = float(ref @ ours)
        worst_clap = min(worst_clap, cos_clap)

        # event-style and section-style tags from the shipped data
        _, z_es = timeline.tag_scores(ref[None], E_es, et)
        d = ref @ E_events.T - consts["event_tag_center"] * background
        z_ev = (d - d.mean()) / (d.std() + 1e-9)
        top_es = list(np.argsort(-z_es[0])[:3])
        top_ev = list(np.argsort(-z_ev)[:3])
        # use OUR embedding for ours
        d2 = ours @ E_events.T - consts["event_tag_center"] * background
        z_ev2 = (d2 - d2.mean()) / (d2.std() + 1e-9)
        top_ev2 = list(np.argsort(-z_ev2)[:3])
        same_events = top_es == top_ev2
        es_terms = ev.top_terms(ref, k=8)
        cos_t = ours @ E_terms.T
        u = cos_t - term_bias
        z_t = (u - u.mean()) / (u.std() + 1e-9)
        top_t = [term_names[i] for i in np.argsort(-z_t)[:8]]
        same_terms = [t_[0] for t_ in es_terms] == top_t
        tags_total += 2
        tags_same += int(same_events) + int(same_terms)

        # AST
        y = audio.resample(audio.to_mono(x), SR48, SR16).astype(np.float32)
        p_ref = a.probs([x], reduce="max")[0]
        t = time.perf_counter()
        pw = [ast_sess.run(None, {"waveform": w[None]})[1][0] for w in ast_windows(y)]
        ast_ms.append((time.perf_counter() - t) * 1000 / len(pw))
        p_ours = np.max(pw, axis=0)
        dmax = float(np.abs(p_ref - p_ours).max())
        worst_ast = max(worst_ast, dmax)
        top5_ref = [labels[i] for i in np.argsort(-p_ref)[:5]]
        top5_ours = [labels[i] for i in np.argsort(-p_ours)[:5]]
        print(f"{name:24s} {len(x) / SR48:5.2f}s clap cos {cos_clap:.6f}  event top3 same {same_events}  "
              f"vocab top8 same {same_terms}  | ast max|dp| {dmax:.5f} top5 same {top5_ref == top5_ours}")
        report["cases"][name] = {
            "seconds": len(x) / SR48,
            "clap_cosine_onnx_vs_pytorch_fp32": cos_clap,
            "event_top3_same_as_earshot": same_events,
            "vocab_top8_same_as_earshot": same_terms,
            "ast_max_abs_prob_diff": dmax,
            "ast_top5_same": top5_ref == top5_ours,
        }

    print(f"\nCLAP worst cosine {worst_clap:.6f}; tag lists identical in {tags_same}/{tags_total}")
    print(f"AST worst max |prob diff| {worst_ast:.5f}")
    print(f"CPU latency per window (12 threads): clap {np.median(clap_ms):.0f} ms, ast {np.median(ast_ms):.0f} ms")

    # ---- reference data
    refs = {
        "film_window_0_10s": ("film_audio.wav, samples 0..480000 (0-10 s): a 10 s section window", film[:CLAP_WINDOW]),
        "bursts_event_0p5s": ("bursts.wav, 0.5 s excerpt starting 20 ms before the sharpest onset: an event excerpt "
                              "(repeat-padded to 10 s by the graph)", cases["bursts_event_0p5s"]),
        "sweep_full": ("sweep.wav, the whole 8 s: a tonal clip", sweep),
    }
    index = {
        "format": 1,
        "byte_order": "little-endian float32 raw files",
        "earshot": {"commit": "591fa3e028032e6dce56620a20e932e35667e8d8", "precision": "fp32 PyTorch (not bf16)"},
        "tolerances": {
            "clap_embedding_cosine": ">= 0.9999 expected between the fp16-weight ONNX graph and these fp32 references",
            "ast_probability_abs": "< 0.01",
            "mel_features_abs": "< 1e-3 dB for clap_mel, < 1e-3 for ast_fbank (float32 vs float64 reference)",
        },
        "cases": {},
    }
    for key, (desc, x) in refs.items():
        x = np.asarray(x, np.float32)
        x.astype("<f4").tofile(refdir / f"{key}.wav48k.f32")
        y = audio.resample(audio.to_mono(x), SR48, SR16).astype(np.float32)
        y.astype("<f4").tofile(refdir / f"{key}.wav16k.f32")

        emb = c.embed_audio([x], pad="repeatpad")[0]
        emb.astype("<f4").tofile(refdir / f"{key}.clap_embedding.f32")
        padded = c._prep(x, "repeatpad")
        mel = c.proc(audio=[padded], sampling_rate=SR48, return_tensors="np")["input_features"]
        mel.astype("<f4").tofile(refdir / f"{key}.clap_mel.f32")

        yy = np.pad(y, (0, max(0, 1600 - len(y))))
        fb = a.fe([yy], sampling_rate=SR16, return_tensors="np")["input_values"]
        fb.astype("<f4").tofile(refdir / f"{key}.ast_fbank.f32")
        import torch

        with torch.inference_mode():
            logits = a.model(input_values=torch.from_numpy(fb)).logits[0].float().numpy()
        logits.astype("<f4").tofile(refdir / f"{key}.ast_logits.f32")
        probs = a.probs([x], reduce="max")[0]
        probs.astype("<f4").tofile(refdir / f"{key}.ast_probs.f32")

        cos_e, z_e = timeline.tag_scores(emb[None], E_es, et)
        sections = ev.calibrate(emb[None])
        z_plain = timeline._zscores(emb[None], ev.E)
        entry = {
            "description": desc,
            "files": {
                "wav48k": {"file": f"{key}.wav48k.f32", "shape": [1, len(x)], "graph_input": "clap waveform",
                           "note": "wav48k may be shorter or longer than 10 s; the graph repeat-pads"},
                "wav16k": {"file": f"{key}.wav16k.f32", "shape": [1, len(y)], "graph_input": "ast waveform",
                           "note": "earshot.audio.resample (soxr HQ) of wav48k"},
                "clap_mel": {"file": f"{key}.clap_mel.f32", "shape": list(mel.shape),
                             "note": "HF ClapFeatureExtractor(repeatpad, rand_trunc) input_features; what the CLAP "
                                     "encoder receives after the in-graph front end"},
                "clap_embedding": {"file": f"{key}.clap_embedding.f32", "shape": [512]},
                "ast_fbank": {"file": f"{key}.ast_fbank.f32", "shape": list(fb.shape),
                              "note": "ASTFeatureExtractor input_values, already normalised; what the AST "
                                      "encoder receives after the in-graph front end"},
                "ast_logits": {"file": f"{key}.ast_logits.f32", "shape": [527]},
                "ast_probs": {"file": f"{key}.ast_probs.f32", "shape": [527],
                              "note": "earshot ast.probs reduce=max, so the max over windows if > 10.24 s"},
            },
            "earshot": {
                "event_tags_top3": [
                    {"phrase": et[k], "kind": str(ek[k]), "z": round(float(z_e[0][k]), 4),
                     "cosine": round(float(cos_e[0][k]), 5)}
                    for k in np.argsort(-z_e[0])[:3]
                ],
                "vocab_top8_calibrated": [
                    {"term": n_, "category": cat_, "z": z_, "cosine": cos_} for n_, cat_, z_, cos_ in ev.top_terms(emb, k=8)
                ],
                "section_tags_plain_z_top2_per_category": {
                    cat: [
                        {"term": ev.names[i], "z": round(float(z_plain[1][0][i]), 4),
                         "cosine": round(float(z_plain[0][0][i]), 5)}
                        for i in [j for j in np.argsort(-z_plain[1][0]) if ev.cat_of[ev.names[j]] == cat][:2]
                    ]
                    for cat in consts["section_categories"]
                },
                "ast_top10": [{"label": labels[i], "p": round(float(probs[i]), 5)} for i in np.argsort(-probs)[:10]],
                "ast_speech_music_silence": {k: round(float(probs[ast_idx[k]]), 5) for k in ("Speech", "Music", "Silence")},
            },
        }
        index["cases"][key] = entry
        print(f"refdata {key}: event top {entry['earshot']['event_tags_top3'][0]['phrase']!r}; "
              f"AST top {entry['earshot']['ast_top10'][0]['label']!r}")
    (refdir / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    (refdir / "validation.json").write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
