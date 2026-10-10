#!/usr/bin/env python3
r"""Export Chatterbox Multilingual's S3Gen decoder as three ONNX graphs, with the solver left out.

    ./fetch-chatterbox.py
    uv run --python 3.11 --index-strategy unsafe-best-match \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        --with chatterbox-tts==0.1.7 --with onnx --with safetensors \
        ./export-chatterbox-s3gen.py

Run fetch-chatterbox.py first: this writes into the model directory it creates, and refreshes the
SHA-256 sidecars there. Needs torch (CPU build is enough), chatterbox-tts for the S3Gen modules,
onnx and safetensors. The checkpoint is cached under ../staging/.cache.

onnx-community's conditional_decoder.onnx unrolls the 10-step flow-matching solver, so every weight
of the estimator is consumed ten times. ONNX Runtime's allocation planner then needs ~1 minute to
create the session. The same maths is exported here as three graphs and Drift runs the Euler loop:

  s3gen_prepare.onnx    speech_tokens [1,N] int64, speaker_embeddings [1,192], speaker_features [1,F,80]
                        -> mu [1,80,T], spks [1,80], cond [1,80,T]            (T = 2 * (prompt + N))
  s3gen_estimator.onnx  x, mu, cond [1,80,T], t [1], spks [1,80], cfg_rate [1] -> dphi_dt [1,80,T]
                        one estimator call; classifier-free guidance is folded in (batch of two, the
                        second with mu, spks and cond zeroed): (1+cfg)*cond_out - cfg*uncond_out
  s3gen_vocoder.onnx    mel [1,80,T'] (the prompt frames already dropped) -> waveform [1,480*T']
                        HiFT vocoder with its harmonic source generator; the source noise is drawn
                        inside the graph, as in the original

Noise: upstream draws the solver's starting noise with randn_like on every call, and so did the
original graph, so nothing is fixed. Drift draws x0 ~ N(0, temperature^2) itself.

Differences from the original graph: the vocoder clamps to +-0.99 as upstream's HiFT does (the
original left that out). Otherwise nothing that changes the result: the attention and conv masks are
all ones for a single unpadded sequence, so they are dropped; the first Euler step of the original
fed an all-zero mask to the unconditional branch, an accident of its hand-unrolled first step that
the upstream solver does not have.

Sources and licences:
  - Resemble AI Chatterbox (MIT), https://github.com/resemble-ai/chatterbox: the S3Gen modules.
  - Checkpoint: ResembleAI/chatterbox on Hugging Face, s3gen.safetensors, the file that holds the
    same weights as the s3gen.pt mtl_tts.py loads for the multilingual model.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

REVISION = "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18"
CHECKPOINT_URL = f"https://huggingface.co/ResembleAI/chatterbox/resolve/{REVISION}/s3gen.safetensors"
CHECKPOINT_SHA256 = "2b78103c654207393955e4900aac14a12de8ef25f4b09424f1ef91941f161d4e"

OPSET = 17
N_FFT = 16
HOP = 4
UPSAMPLE = 480  # samples per mel frame: 8 * 5 * 3 vocoder upsampling, times the iSTFT hop
MEL_BINS = 80
N_TRIM = 24000 // 50


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_checkpoint() -> Path:
    dest = CACHE / f"chatterbox-s3gen-{REVISION[:8]}.safetensors"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256_of(dest) == CHECKPOINT_SHA256:
        print(f"cached  {dest.name}")
        return dest
    print(f"fetch   {CHECKPOINT_URL}")
    urllib.request.urlretrieve(CHECKPOINT_URL, dest)
    actual = sha256_of(dest)
    if actual != CHECKPOINT_SHA256:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"sha256 mismatch for the checkpoint\n  expected {CHECKPOINT_SHA256}\n  got      {actual}")
    return dest


def load_s3gen(checkpoint: Path):
    from chatterbox.models.s3gen.s3gen import S3Token2Wav
    from safetensors.torch import load_file

    model = S3Token2Wav()
    result = model.load_state_dict(load_file(str(checkpoint)), strict=False)
    # The speech tokenizer's STFT window is rebuilt by its constructor and is not in the checkpoint.
    if result.unexpected_keys or set(result.missing_keys) - set(S3Token2Wav.ignore_state_dict_missing):
        raise SystemExit(f"unexpected checkpoint layout: {result}")
    return model.eval()


def define_modules():
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class Prepare(nn.Module):
        """Speech tokens and the reference voice to the solver's conditioning."""

        def __init__(self, s3gen):
            super().__init__()
            self.flow = s3gen.flow

        def forward(self, speech_tokens, speaker_embeddings, speaker_features):
            flow = self.flow
            spks = flow.spk_embed_affine_layer(F.normalize(speaker_embeddings, dim=1))
            tokens = flow.input_embedding(torch.clamp(speech_tokens, min=0))
            token_len = torch.full((speech_tokens.size(0),), speech_tokens.size(1), dtype=torch.long)
            encoded, _ = flow.encoder(tokens, token_len)
            mu = flow.encoder_proj(encoded)
            pad = mu.size(1) - speaker_features.size(1)
            cond = F.pad(speaker_features, (0, 0, 0, pad))
            return mu.transpose(1, 2).contiguous(), spks, cond.transpose(1, 2).contiguous()

    def estimate(est, x, mu, t, spks, cond):
        """ConditionalDecoder.forward for an unpadded sequence: every mask is ones."""
        t = est.time_mlp(est.time_embeddings(t).to(t.dtype))
        x = torch.cat([x, mu, spks.unsqueeze(-1).expand(-1, -1, x.shape[-1]), cond], dim=1)

        ones = torch.ones_like(x[:, :1])
        resnet, blocks, downsample = est.down_blocks[0]
        x = resnet(x, ones, t)
        x = x.permute(0, 2, 1).contiguous()
        for block in blocks:
            x = block(hidden_states=x, attention_mask=None, timestep=t)
        skip = x.permute(0, 2, 1).contiguous()
        x = downsample(skip)

        for resnet, blocks in est.mid_blocks:
            x = resnet(x, ones, t)
            x = x.permute(0, 2, 1).contiguous()
            for block in blocks:
                x = block(hidden_states=x, attention_mask=None, timestep=t)
            x = x.permute(0, 2, 1).contiguous()

        resnet, blocks, upsample = est.up_blocks[0]
        x = torch.cat([x[:, :, :skip.shape[-1]], skip], dim=1)
        x = resnet(x, ones, t)
        x = x.permute(0, 2, 1).contiguous()
        for block in blocks:
            x = block(hidden_states=x, attention_mask=None, timestep=t)
        x = upsample(x.permute(0, 2, 1).contiguous())
        x = est.final_block(x, ones)
        return est.final_proj(x)

    class Estimator(nn.Module):
        """One guided Euler derivative: both CFG branches in a batch of two."""

        def __init__(self, s3gen):
            super().__init__()
            self.estimator = s3gen.flow.decoder.estimator

        def forward(self, x, mu, cond, t, spks, cfg_rate):
            zero_mu, zero_cond, zero_spks = torch.zeros_like(mu), torch.zeros_like(cond), torch.zeros_like(spks)
            out = estimate(
                self.estimator,
                torch.cat([x, x]),
                torch.cat([mu, zero_mu]),
                torch.cat([t, t]),
                torch.cat([spks, zero_spks]),
                torch.cat([cond, zero_cond]),
            )
            return (1.0 + cfg_rate) * out[:1] - cfg_rate * out[1:]

    class Stft(nn.Module):
        """torch.stft(n_fft, hop, hann, center=True, reflect) as a convolution, real and imaginary stacked."""

        def __init__(self):
            super().__init__()
            window = torch.hann_window(N_FFT, periodic=True).double()
            n = torch.arange(N_FFT).double()
            k = torch.arange(N_FFT // 2 + 1).double().unsqueeze(1)
            angle = 2 * np.pi * k * n / N_FFT
            basis = torch.cat([torch.cos(angle) * window, -torch.sin(angle) * window]).float()
            self.register_buffer("basis", basis.unsqueeze(1))

        def forward(self, wave):
            x = F.pad(wave.unsqueeze(1), (N_FFT // 2, N_FFT // 2), mode="reflect")
            return F.conv1d(x, self.basis, stride=HOP)

    class Istft(nn.Module):
        """torch.istft(n_fft, hop, hann, center=True) as a transposed convolution."""

        def __init__(self):
            super().__init__()
            window = torch.hann_window(N_FFT, periodic=True).double()
            n = torch.arange(N_FFT).double()
            bins = N_FFT // 2 + 1
            k = torch.arange(bins).double().unsqueeze(1)
            weight = torch.full((bins, 1), 2.0).double()
            weight[0] = 1.0
            weight[-1] = 1.0
            angle = 2 * np.pi * k * n / N_FFT
            basis = torch.cat([weight * torch.cos(angle), -weight * torch.sin(angle)]) / N_FFT * window
            self.register_buffer("basis", basis.float().unsqueeze(1))
            self.register_buffer("window_sq", (window ** 2).float().view(1, 1, N_FFT))

        def forward(self, spec):
            frames = spec.size(-1)
            wave = F.conv_transpose1d(spec, self.basis, stride=HOP)
            envelope = F.conv_transpose1d(torch.ones(1, 1, frames), self.window_sq, stride=HOP)
            wave = wave / envelope
            return wave[:, 0, N_FFT // 2:-(N_FFT // 2)]

    class Vocoder(nn.Module):
        """HiFT mel to waveform, source generator included.

        With inject_noise the three random draws become inputs, which is how the export is checked
        against a reference: the graph is the same.
        """

        def __init__(self, s3gen, inject_noise=False):
            super().__init__()
            self.hift = s3gen.mel2wav
            self.stft = Stft()
            self.istft = Istft()
            self.inject_noise = inject_noise
            self.register_buffer("trim_fade", s3gen.trim_fade.clone())

        def sine_gen(self, f0, phase, noise):
            gen = self.hift.m_source.l_sin_gen
            harmonics = torch.arange(1, gen.harmonic_num + 2, dtype=f0.dtype).view(1, -1, 1)
            rate = f0 * harmonics / gen.sampling_rate
            cycles = torch.cumsum(rate, dim=-1)
            theta = 2 * np.pi * (cycles - torch.floor(cycles))
            phase = torch.cat([torch.zeros_like(phase[:, :1]), phase[:, 1:]], dim=1)
            sine = gen.sine_amp * torch.sin(theta + phase)
            uv = (f0 > gen.voiced_threshold).to(torch.float32)
            noise_amp = uv * gen.noise_std + (1 - uv) * gen.sine_amp / 3
            return sine * uv + noise_amp * noise

        def forward(self, mel, phase=None, noise=None):
            hift = self.hift
            f0 = hift.f0_predictor(mel)
            s = hift.f0_upsamp(f0[:, None]).transpose(1, 2)
            f0_up = s.transpose(1, 2)
            if not self.inject_noise:
                harmonics = hift.m_source.l_sin_gen.harmonic_num + 1
                phase = (torch.rand(1, harmonics, 1) * 2 - 1) * np.pi
                noise = torch.randn(1, harmonics, f0_up.shape[-1])
            sines = self.sine_gen(f0_up, phase, noise).transpose(1, 2)
            source = torch.tanh(hift.m_source.l_linear(sines)).transpose(1, 2)
            source_spec = self.stft(source.squeeze(1))

            x = hift.conv_pre(mel)
            for i in range(hift.num_upsamples):
                x = F.leaky_relu(x, hift.lrelu_slope)
                x = hift.ups[i](x)
                if i == hift.num_upsamples - 1:
                    x = hift.reflection_pad(x)
                x = x + hift.source_resblocks[i](hift.source_downs[i](source_spec))
                xs = hift.resblocks[i * hift.num_kernels](x)
                for j in range(1, hift.num_kernels):
                    xs = xs + hift.resblocks[i * hift.num_kernels + j](x)
                x = xs / hift.num_kernels
            x = hift.conv_post(F.leaky_relu(x))

            bins = N_FFT // 2 + 1
            magnitude = torch.clamp(torch.exp(x[:, :bins]), max=1e2)
            angle = torch.sin(x[:, bins:])
            wave = self.istft(torch.cat([magnitude * torch.cos(angle), magnitude * torch.sin(angle)], dim=1))
            fade = self.trim_fade.size(0)
            wave = torch.cat([wave[:, :fade] * self.trim_fade, wave[:, fade:]], dim=1)
            return torch.clamp(wave, -hift.audio_limit, hift.audio_limit)

    return Prepare, Estimator, Vocoder, estimate


def export(out: Path, checkpoint: Path) -> None:
    import onnx
    import torch

    Prepare, Estimator, Vocoder, _ = define_modules()
    s3gen = load_s3gen(checkpoint)

    tokens = torch.randint(0, 6561, (1, 40))
    embedding = torch.randn(1, 192)
    features = torch.randn(1, 160, MEL_BINS)
    frames = 2 * (80 + 40)

    def save(module, args, name, inputs, outputs, axes):
        path = out / name
        with torch.no_grad():
            torch.onnx.export(module, args, str(path), input_names=inputs, output_names=outputs,
                              dynamic_axes=axes, opset_version=OPSET, dynamo=False)
        onnx.checker.check_model(str(path))
        print(f"wrote   {name}  ({path.stat().st_size / 1e6:.1f} MB)")

    save(Prepare(s3gen), (tokens, embedding, features), "s3gen_prepare.onnx",
         ["speech_tokens", "speaker_embeddings", "speaker_features"], ["mu", "spks", "cond"],
         {"speech_tokens": {1: "tokens"}, "speaker_features": {1: "prompt_frames"},
          "mu": {2: "frames"}, "cond": {2: "frames"}})

    x = torch.randn(1, MEL_BINS, frames)
    save(Estimator(s3gen), (x, torch.randn_like(x), torch.randn_like(x), torch.tensor([0.3]),
                            torch.randn(1, MEL_BINS), torch.tensor([0.7])), "s3gen_estimator.onnx",
         ["x", "mu", "cond", "t", "spks", "cfg_rate"], ["dphi_dt"],
         {"x": {2: "frames"}, "mu": {2: "frames"}, "cond": {2: "frames"}, "dphi_dt": {2: "frames"}})

    save(Vocoder(s3gen), (torch.randn(1, MEL_BINS, 75),), "s3gen_vocoder.onnx", ["mel"], ["waveform"],
         {"mel": {2: "frames"}, "waveform": {1: "samples"}})


def main() -> int:
    out = STAGING / "chatterbox-multilingual" / "models" / "chatterbox-multilingual"
    if not (out / "constants.json").exists():
        raise SystemExit("run fetch-chatterbox.py first")
    export(out, fetch_checkpoint())
    staging_hashes.write_sidecars_under(STAGING / "chatterbox-multilingual")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
