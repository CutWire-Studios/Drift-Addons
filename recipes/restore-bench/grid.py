import sys, os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'staging', '.cache', 'restore-bench'))
from PIL import Image, ImageDraw
content, kind, scale = sys.argv[1], sys.argv[2], int(sys.argv[3]); names = sys.argv[4:]
x, y, w, h = {'anime': (190, 20, 384, 216), 'live': (770, 40, 384, 216), 'cg': (520, 60, 384, 216)}[content]
tiles = []
src = Image.open(f'out/input_x{scale}_{content}_{kind}.png').convert('RGB')
tiles.append(('bicubic', src.resize((src.width*scale, src.height*scale), Image.BICUBIC) if scale > 1 else src))
tiles.append(('HR', Image.open(f'hr_{content}.png').convert('RGB')))
for n in names: tiles.append((n, Image.open(f'out/{n}_{content}_{kind}.png').convert('RGB')))
cols = 4; rows = (len(tiles) + cols - 1) // cols
g = Image.new('RGB', (cols*w, rows*(h+16)), 'white'); d = ImageDraw.Draw(g)
for i, (n, im) in enumerate(tiles):
    cx, cy = (i % cols)*w, (i // cols)*(h+16)
    g.paste(im.crop((x, y, x+w, y+h)), (cx, cy+16)); d.text((cx+4, cy+2), n, fill='black')
g.save(f'/tmp/grid_{content}_{kind}_x{scale}.png')
