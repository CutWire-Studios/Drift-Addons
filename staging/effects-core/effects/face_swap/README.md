# Face Swap

Maps a face from a still photo onto the face tracked in the clip. The clip's baked
`FaceTrack` supplies 468 mesh points per frame as vertex positions; the same landmarker run
once over the photo supplies the matching 468 points as texture coordinates. Drawing
MediaPipe's tessellation with those two sets is the whole swap.

This is a geometric warp, not a neural face swap. Identity, skin texture, teeth and eyes all
come from the one photo, so it holds up to roughly ±30° of head turn and degrades past that —
a 2D still has no data for what is behind the nose. `Keep Eyes` and `Keep Mouth` let the
subject's real eyes and mouth through, which is what lets talking and blinking still read.

Intended for the same kind of edit as the rest of the Funny category: memes, reaction clips,
putting a friend's face on a cat. Use it on people who agreed to be in the edit.

## Requirements

- The **face-model** addon and the ONNX Runtime addon (same as every other face effect).
- Face tracking baked on the clip — Effects → Detect faces.
- A photo with one clearly visible, reasonably frontal face.

## Parameters

| Parameter | Effect |
|---|---|
| Face photo | The still to take the face from. Landmarked once when picked, then cached. |
| Opacity | Blend of the whole swap over the original frame. |
| Edge Feather | How far in from the face oval the swap fades out. Raise it when the hairline or jaw boundary shows. |
| Match Lighting | Transfers the clip's low-frequency lighting onto the photo. The main defence against an obviously pasted-on face; drop it only when the photo already matches. |
| Keep Eyes | Lets the tracked face's own eyes through, so blinks survive. |
| Keep Mouth | Lets the tracked face's own mouth through, so speech survives. |
| Face | Which tracked face to replace when the clip has more than one. |

## `mediapipe_face.bin`

MediaPipe's canonical 468-vertex face model, baked by `tools/convert_face_mesh.py` from the
Apache-2.0 `canonical_face_model.obj`. Only the triangle list is read at render time — vertex
positions come from the track — but the rest positions are written in the same head space as
`face_mesh_3d/sfm_face.bin`, so the two bins are interchangeable for debugging.

Same `"DRFM"` layout documented in `../face_mesh_3d/README.md`, with `handleCount` 0: the swap
never calls `warpFaceMesh`, because the tracked positions it would solve for are already in
`FaceAnchors::mesh`.

### Head space

| Axis | Direction |
|------|-----------|
| Origin | Inner-eye midpoint (MediaPipe 133 / 362) |
| +X | Image-right |
| +Y | Toward forehead |
| +Z | Toward the viewer |
| Width ±0.5 | Interior face; the oval reaches ±0.68 |

The canonical model already uses these axes, so the converter asserts the orientation rather
than remapping it — an upstream export that changed handedness fails the bake instead of
silently rendering mirrored.
