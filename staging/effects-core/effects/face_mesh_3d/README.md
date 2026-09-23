# 3D Face Mesh rest pose

`sfm_face.bin` is the CPU rest-pose mesh for **3D Face Mesh**. It is the public
Surrey Face Model reference remapped into
Drift head space. At draw time it is inverse-distance warped toward
MediaPipe's 468-point mesh.

## Head space

Same frame as the tracked head pose (origin at the inner-eye midpoint). Scaled so the
**interior ibug handles** span one head-width (`x` extent 1); the ear wrap extends past ±0.5:

| Axis | Direction |
|------|-----------|
| Origin | Inner-eye midpoint (ibug 40 / 43) |
| +X | Image-right |
| +Y | Toward forehead |
| +Z | Toward the viewer |
| Width ±0.5 | Interior face (ibug handles); ears extend past this |

## Conversion

- Remap axes (Y-up SFM → image-right / forehead / toward viewer) and pivot to the
  inner-eye midpoint
- Scale so interior ibug x-span is 1
- Warp handles: ibug 9–68 that exist on the 845-vert mesh, mapped to MediaPipe,
  plus 234 / 454 on the most lateral ear-front vertices and 10 on the hairline
  (ibug 1–8 and 10–17 are not on this reference)
- At draw time the warp first fits a uniform scale to those handles, then
  inverse-distance warps the residual so the hairline and chin follow the
  tracked face instead of staying at SFM rest size. Inner-lip handles are
  partitioned by mesh topology so a closed rest mouth can open (unfiltered IDW
  would average the coincident upper/lower verts and zip the cupid's bow).

## Bin format (`sfm_face.bin`, little-endian)

| Field | Type |
|-------|------|
| magic | 4 bytes `"DRFM"` |
| version | uint32 `1` |
| vertCount, indexCount, handleCount | uint32 × 3 |
| positions | float32 × vertCount × 3 (x, y, z) |
| indices | uint32 × indexCount (CCW triangles, +Z toward viewer) |
| handles | uint16 mediapipeIndex, uint16 restVertexIndex, × handleCount |
