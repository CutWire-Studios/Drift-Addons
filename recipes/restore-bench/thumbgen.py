"""Picker thumbnails: the model on a crop of the footage it is made for, split against bicubic.

The input is the high-resolution crop scaled down by the model's factor and H.264-compressed at a
quality typical of web video, so the right half shows what the model does to footage people have.
1x (clean-up) models get the full-size crop compressed hard instead.
"""
import os, subprocess, sys
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw

# Inputs, models and outputs live in the staging cache, not in the repo.
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'staging', '.cache', 'restore-bench')
THUMBS = os.path.join(HERE, 'thumbs'); os.makedirs(THUMBS, exist_ok=True)
W, H = 480, 270
CROPS = {'anime': (190, 20, 384, 216), 'live': (700, 50, 384, 216), 'cg': (520, 60, 384, 216)}
MARGIN = 64  # context around the crop, so the model's edges stay out of the picture
CRF = {1: 34, 2: 23, 4: 18}

def h264(im, crf):
    src, enc, dec = '/tmp/_t.png', '/tmp/_t.mp4', '/tmp/_t_dec.png'
    im.save(src)
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', src, '-c:v', 'libx264',
                    '-crf', str(crf), '-pix_fmt', 'yuv420p', enc], check=True)
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', enc, '-frames:v', '1', dec], check=True)
    return Image.open(dec).convert('RGB')

def run(path, im):
    o = ort.SessionOptions(); o.intra_op_num_threads = os.cpu_count()
    s = ort.InferenceSession(path, o, providers=['CPUExecutionProvider'])
    i = s.get_inputs()[0]
    dt = np.float16 if i.type == 'tensor(float16)' else np.float32
    a = np.asarray(im, np.float32) / 255
    h, w = a.shape[:2]; ph, pw = -h % 16, -w % 16
    x = np.pad(a, ((0, ph), (0, pw), (0, 0)), mode='edge').transpose(2, 0, 1)[None].astype(dt)
    y = s.run(None, {i.name: x})[0][0].astype(np.float32).transpose(1, 2, 0)
    k = y.shape[0] // (h + ph)
    return Image.fromarray((np.clip(y[:h * k, :w * k], 0, 1) * 255 + 0.5).astype(np.uint8))

def thumb(model, content, scale):
    hr = Image.open(os.path.join(HERE, f'hr_{content}.png')).convert('RGB')
    x, y, w, h = CROPS[content]
    m = MARGIN
    region = hr.crop((x - m, y - m, x + w + m, y + h + m))
    lr = region.resize((region.width // scale, region.height // scale), Image.BICUBIC) if scale > 1 else region
    lr = h264(lr, CRF[scale])
    before = lr.resize(region.size, Image.BICUBIC) if scale > 1 else lr
    after = run(model, lr)
    box = (m, m, m + w, m + h)
    a = before.crop(box).resize((W, H), Image.LANCZOS)
    b = after.crop(box).resize((W, H), Image.LANCZOS)
    a.paste(b.crop((W // 2, 0, W, H)), (W // 2, 0))
    ImageDraw.Draw(a).rectangle((W // 2 - 1, 0, W // 2, H), fill=(255, 255, 255))
    return a

if __name__ == '__main__':
    for spec in sys.argv[1:]:  # model.onnx:content:scale:outname
        model, content, scale, out = spec.split(':')
        thumb(os.path.join(HERE, 'models', model), content, int(scale)).save(
            os.path.join(THUMBS, out + '.jpg'), quality=86, optimize=True, progressive=True)
        print('thumb', out, flush=True)
