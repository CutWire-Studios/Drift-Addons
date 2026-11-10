# Store catalog

Metadata for the Drift Extras store. `packer/catalog.py` validates these files, compiles them into one `catalog.json` and uploads it; the Worker serves it at `GET /v1/catalog`. Text changes never need a repack.

## Files

- `categories.json`: list of `{id, title, subtitle, icon, order}`.
- `collections.json`: Discover shelves, `{id, title, addons[]}`.
- `addons/<name>.json`: one entry per addon, or per platform family via `match`.
- `media/`: images referenced by `images[].src`. Filenames are content-hashed on publish.

Addons without an entry are ignored by the store (the validator warns).

## Entry

```
id | match      exact addon id, or a glob such as "onnxruntime.cpu.*" (one card for all platform builds)
name            overrides the package's own name wherever Drift shows it
description     overrides the package's description
details         overrides the package's details
tagline         one line, 60 characters at most
summary         2-3 sentences
categories[]    category ids
keywords[]      search terms
icon, accent    icon name from the list below; optional accent colour
useCases[]      "What it's for" bullets
howTo[]         ordered steps
unlocks[]       {label, location}
requires[]      {id, reason?} or {kind, prefer:{<platform>: id}, default, reason}
recommends[]    {id, reason}; never auto-installed
images[]        {src, caption, width, height}; src is relative to catalog/media/
links[]         {label, url}
hidden, order
```

Platform keys in `prefer`: android-arm64, linux-arm64, linux-x64, osx-arm64, osx-x64, win-arm64, win-x64.

Icon names: star, sparkles, palette, type, captions, audio, mic, scissors, wand, smile, brain, bot, cpu, zap, layers, file.

## Compiled output

`name`, `description` and `details` are merged by the Worker into `/v1/index` rows, so text changes never need a repack.

`{schema: 1, revision, generated, categories, collections, entries}`. `revision` is the first 16 hex of a SHA-256 over the content and is the response ETag. Compiled `images[].src` is the hashed filename, served from `/v1/media/<src>`. Clients must ignore unknown fields; breaking changes bump `schema`.

## R2 layout

- `catalog/catalog.json`, plus optional `catalog/catalog.<lang>.json` chosen from `Accept-Language`
- `catalog/media/<stem>.<hash8>.<ext>`
