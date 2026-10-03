"""Speed and quality benchmark for the restore models, on ONNX Runtime CPU like Drift."""
import glob, json, os, subprocess, sys, time
import numpy as np
import onnxruntime as ort
from PIL import Image

# Inputs, models and outputs live in the staging cache, not in the repo.
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'staging', '.cache', 'restore-bench')
OUT = os.path.join(HERE, 'out'); os.makedirs(OUT, exist_ok=True)
THREADS = os.cpu_count()
CONTENT = ['anime', 'live', 'cg']

def session(path):
    o = ort.SessionOptions(); o.intra_op_num_threads = THREADS
    return ort.InferenceSession(path, o, providers=['CPUExecutionProvider'])

def run(s, img):  # img HxWx3 float32 0..1; edge-padded to a multiple of 16 the way Drift's tiles are
    i = s.get_inputs()[0]
    dt = np.float16 if i.type == 'tensor(float16)' else np.float32
    h, w = img.shape[:2]
    ph, pw = -h % 16, -w % 16
    x = np.pad(img, ((0, ph), (0, pw), (0, 0)), mode='edge').transpose(2, 0, 1)[None].astype(dt)
    y = s.run(None, {i.name: x})[0][0].astype(np.float32).transpose(1, 2, 0)
    k = y.shape[0] // (h + ph)
    return np.clip(y[:h * k, :w * k], 0, 1)

def load(p): return np.asarray(Image.open(p).convert('RGB'), dtype=np.float32) / 255
def save(a, p): Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)).save(p)

def h264(a, crf):
    src = os.path.join(OUT, '_tmp.png'); save(a, src)
    enc = os.path.join(OUT, '_tmp.mp4'); dec = os.path.join(OUT, '_tmp_dec.png')
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', src, '-c:v', 'libx264',
                    '-preset', 'medium', '-crf', str(crf), '-pix_fmt', 'yuv420p', enc], check=True)
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', enc, '-frames:v', '1', dec], check=True)
    return load(dec)

def psnr_y(a, b):
    w = np.array([0.299, 0.587, 0.114], np.float32)
    ya, yb = a @ w, b @ w
    mse = np.mean((ya - yb) ** 2)
    return 10 * np.log10(1 / max(mse, 1e-10))

def downscale(a, s):
    im = Image.fromarray((a * 255 + 0.5).astype(np.uint8))
    return np.asarray(im.resize((a.shape[1] // s, a.shape[0] // s), Image.BICUBIC), np.float32) / 255

def bicubic_up(a, s):
    im = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8))
    return np.asarray(im.resize((a.shape[1] * s, a.shape[0] * s), Image.BICUBIC), np.float32) / 255

def speed(s, scale):
    i = s.get_inputs()[0]
    dt = np.float16 if i.type == 'tensor(float16)' else np.float32
    x = np.random.default_rng(0).random((1, 3, 544, 544)).astype(dt)  # Drift's 512 tile + 16 px context
    s.run(None, {i.name: x})
    ts = []
    for _ in range(3):
        t = time.perf_counter(); s.run(None, {i.name: x}); ts.append(time.perf_counter() - t)
    tile = float(np.median(ts))
    return tile, tile / (512 * 512 / 1e6)

def main():
    only = set(sys.argv[1:])
    hr = {c: load(os.path.join(HERE, f'hr_{c}.png')) for c in CONTENT}
    lr = {}
    results = {}
    for path in sorted(glob.glob(os.path.join(HERE, 'models', '*.onnx'))):
        name = os.path.basename(path)[:-5]
        if only and name.split('.')[0] not in only:
            continue
        s = session(path)
        y = run(s, np.full((64, 64, 3), 0.5, np.float32))
        scale = y.shape[0] // 64
        tile, spm = speed(s, scale)
        r = {'scale': scale, 'tile_s': round(tile, 3), 's_per_mp': round(spm, 3), 'psnr': {}}
        for c in CONTENT:
            for kind, crf in (('clean', None), ('h264', 30)):
                key = (c, scale, kind)
                if key not in lr:
                    base = downscale(hr[c], scale) if scale > 1 else hr[c]
                    lr[key] = h264(base, crf if scale > 1 else 34) if crf else base
                inp = lr[key]
                if scale == 1 and kind == 'clean':
                    continue
                out = run(s, inp)
                r['psnr'][f'{c}/{kind}'] = round(float(psnr_y(out, hr[c])), 2)
                bic = bicubic_up(inp, scale) if scale > 1 else inp
                r['psnr'][f'{c}/{kind}/bicubic'] = round(float(psnr_y(bic, hr[c])), 2)
                save(out, os.path.join(OUT, f'{name}_{c}_{kind}.png'))
                lp = os.path.join(OUT, f'input_x{scale}_{c}_{kind}.png')
                if not os.path.exists(lp):
                    save(inp, lp)
        results[name] = r
        print(name, json.dumps(r), flush=True)
    path = os.path.join(HERE, 'results.json')
    old = json.load(open(path)) if os.path.exists(path) else {}
    old.update(results)
    json.dump(old, open(path, 'w'), indent=1)

main()
