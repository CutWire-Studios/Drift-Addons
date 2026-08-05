"""Minimal SigV4 multipart upload to R2's S3-compatible endpoint.

`wrangler r2 object put` refuses anything over 300 MiB, which rules it out for the Whisper
packages. Rather than add boto3, this signs the three multipart calls by hand — it is about a
hundred lines and keeps the packer dependency-free like the rest of the scripts.

Credentials come from the environment, or from a KEY=value file under `.secrets/`:

    R2_ACCOUNT_ID=...
    R2_ACCESS_KEY_ID=...
    R2_SECRET_ACCESS_KEY=...

Default file is `r2.env` (publish / catalogue bucket). Callers can pass another path
(e.g. `r2_lfs.env` for the private LFS bucket). Bucket names live in `.secrets/config.env`.
"""

import hashlib
import hmac
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REGION = "auto"
SERVICE = "s3"
PART_SIZE = 100 * 1024 * 1024
SECRETS_DIR = Path(__file__).parent.parent / ".secrets"
SECRETS = SECRETS_DIR / "r2.env"
# Thread-local-ish override for scripts that talk to a different bucket/token.
_secrets_path: Path | None = None


def use_secrets(path: Path | str | None) -> None:
    """Select which `.secrets/*.env` file credentials() reads (None = default r2.env)."""
    global _secrets_path
    _secrets_path = Path(path) if path else None


def credentials() -> tuple[str, str, str]:
    values = dict(os.environ)
    secrets_file = _secrets_path or SECRETS
    if secrets_file.exists():
        for line in secrets_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                # File wins over ambient env so a publish token in the shell cannot
                # accidentally talk to the LFS bucket with the wrong key.
                values[key.strip()] = value.strip()

    try:
        return (values["R2_ACCOUNT_ID"], values["R2_ACCESS_KEY_ID"], values["R2_SECRET_ACCESS_KEY"])
    except KeyError as missing:
        raise SystemExit(
            f"{missing} is not set. Create an R2 API token (Cloudflare dashboard -> R2 -> API ->\n"
            f"Manage API tokens, Object Read & Write) and put the values in {secrets_file}."
        ) from None


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def _signing_key(secret: str, datestamp: str) -> bytes:
    key = _sign(f"AWS4{secret}".encode(), datestamp)
    key = _sign(key, REGION)
    key = _sign(key, SERVICE)
    return _sign(key, "aws4_request")


def _request(method: str, account: str, access_key: str, secret: str, path: str,
             query: dict[str, str], body: bytes) -> bytes:
    host = f"{account}.r2.cloudflarestorage.com"
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()

    # Each path segment is encoded, but the separators are not.
    canonical_uri = "/" + "/".join(urllib.parse.quote(p, safe="") for p in path.lstrip("/").split("/"))
    canonical_query = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted(query.items())
    )
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"

    canonical_request = "\n".join(
        [method, canonical_uri, canonical_query, canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{datestamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])
    signature = hmac.new(_signing_key(secret, datestamp), string_to_sign.encode(),
                         hashlib.sha256).hexdigest()

    url = f"https://{host}{canonical_uri}"
    if canonical_query:
        url += f"?{canonical_query}"

    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Host", host)
    request.add_header("x-amz-content-sha256", payload_hash)
    request.add_header("x-amz-date", amz_date)
    request.add_header(
        "Authorization",
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}",
    )

    try:
        with urllib.request.urlopen(request) as response:
            if method == "PUT":
                # Multipart part upload returns the ETag in a header and nothing in the body.
                etag = response.headers.get("ETag")
                return etag.encode() if etag else response.read()
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise FileNotFoundError(path) from error
        raise SystemExit(f"{method} {path} failed: {error.code}\n{error.read().decode()}") from None


def get_bytes(bucket: str, key: str) -> bytes | None:
    account, access_key, secret = credentials()
    try:
        return _request("GET", account, access_key, secret, f"{bucket}/{key}", {}, b"")
    except FileNotFoundError:
        return None


def download_file(bucket: str, key: str, path: Path) -> None:
    """Stream an object to disk without holding the whole body in RAM."""
    account, access_key, secret = credentials()
    host = f"{account}.r2.cloudflarestorage.com"
    object_path = f"{bucket}/{key}"
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_uri = "/" + "/".join(
        urllib.parse.quote(p, safe="") for p in object_path.lstrip("/").split("/")
    )
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join(
        ["GET", canonical_uri, "", canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{datestamp}/{REGION}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])
    signature = hmac.new(_signing_key(secret, datestamp), string_to_sign.encode(),
                         hashlib.sha256).hexdigest()
    url = f"https://{host}{canonical_uri}"
    request = urllib.request.Request(url, method="GET")
    request.add_header("Host", host)
    request.add_header("x-amz-content-sha256", payload_hash)
    request.add_header("x-amz-date", amz_date)
    request.add_header(
        "Authorization",
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    try:
        with urllib.request.urlopen(request) as response, tmp.open("wb") as out:
            while chunk := response.read(8 * 1024 * 1024):
                out.write(chunk)
        tmp.replace(path)
    except urllib.error.HTTPError as error:
        if tmp.exists():
            tmp.unlink()
        if error.code == 404:
            raise FileNotFoundError(object_path) from error
        raise SystemExit(f"GET {object_path} failed: {error.code}\n{error.read().decode()}") from None
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise


def put_file(bucket: str, key: str, path: Path, content_type: str = "application/octet-stream") -> None:
    account, access_key, secret = credentials()
    _request("PUT", account, access_key, secret, f"{bucket}/{key}", {}, path.read_bytes())


def put_path(bucket: str, key: str, path: Path,
             content_type: str = "application/octet-stream") -> None:
    """Upload a file, using multipart when it is larger than one part."""
    if path.stat().st_size > PART_SIZE:
        upload(bucket, key, path, content_type)
    else:
        put_file(bucket, key, path, content_type)


def delete_object(bucket: str, key: str) -> None:
    account, access_key, secret = credentials()
    try:
        _request("DELETE", account, access_key, secret, f"{bucket}/{key}", {}, b"")
    except FileNotFoundError:
        pass


def list_keys(bucket: str, prefix: str = "") -> list[str]:
    return [obj["key"] for obj in list_objects(bucket, prefix)]


def list_objects(bucket: str, prefix: str = "") -> list[dict]:
    """List objects under prefix. Each entry: key, size, etag."""
    account, access_key, secret = credentials()
    out: list[dict] = []
    token: str | None = None
    while True:
        query = {"list-type": "2"}
        if prefix:
            query["prefix"] = prefix
        if token:
            query["continuation-token"] = token
        xml = _request("GET", account, access_key, secret, bucket, query, b"")
        root = ET.fromstring(xml)
        token = None
        truncated = False
        for element in root.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "Contents":
                entry: dict = {"key": "", "size": 0, "etag": ""}
                for child in element:
                    ctag = child.tag.rsplit("}", 1)[-1]
                    if ctag == "Key" and child.text:
                        entry["key"] = child.text
                    elif ctag == "Size" and child.text:
                        entry["size"] = int(child.text)
                    elif ctag == "ETag" and child.text:
                        entry["etag"] = child.text.strip('"')
                if entry["key"]:
                    out.append(entry)
            elif tag == "NextContinuationToken" and element.text:
                token = element.text
            elif tag == "IsTruncated":
                truncated = (element.text or "").lower() == "true"
        if not truncated:
            break
        if not token:
            break
    return out

def _text(xml: bytes, tag: str) -> str:
    root = ET.fromstring(xml)
    # R2 echoes the S3 namespace, so match on the local name.
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == tag:
            return element.text or ""
    raise SystemExit(f"no <{tag}> in response:\n{xml.decode()}")


def upload(bucket: str, key: str, path: Path, content_type: str = "application/octet-stream") -> None:
    account, access_key, secret = credentials()
    object_path = f"{bucket}/{key}"
    total = path.stat().st_size

    started = _request("POST", account, access_key, secret, object_path, {"uploads": ""}, b"")
    upload_id = _text(started, "UploadId")

    parts: list[tuple[int, str]] = []
    try:
        with path.open("rb") as f:
            number = 1
            while chunk := f.read(PART_SIZE):
                etag = _request("PUT", account, access_key, secret, object_path,
                                {"partNumber": str(number), "uploadId": upload_id}, chunk).decode()
                parts.append((number, etag))
                done = min(total, number * PART_SIZE)
                print(f"  part {number}: {done / 1e6:.0f}/{total / 1e6:.0f} MB", flush=True)
                number += 1

        completion = "<CompleteMultipartUpload>" + "".join(
            f"<Part><PartNumber>{n}</PartNumber><ETag>{tag}</ETag></Part>" for n, tag in parts
        ) + "</CompleteMultipartUpload>"
        _request("POST", account, access_key, secret, object_path,
                 {"uploadId": upload_id}, completion.encode())
    except BaseException:
        # Abandoned parts are billed as storage until they are cleaned up, so never leave one open.
        print("aborting multipart upload", file=sys.stderr)
        _request("DELETE", account, access_key, secret, object_path, {"uploadId": upload_id}, b"")
        raise
