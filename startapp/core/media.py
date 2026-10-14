"""Serve access-checked private files (chat attachments) with HTTP Range support for video seeking."""
import mimetypes
import re

from django.http import FileResponse, HttpResponse, StreamingHttpResponse

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 64 * 1024


def _iter_range(handle, start, length):
    handle.seek(start)
    remaining = length
    try:
        while remaining > 0:
            chunk = handle.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        handle.close()


def _secure(response):
    response["X-Content-Type-Options"] = "nosniff"
    # Even if a file were rendered as a document, it could not run scripts on our origin.
    response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'"
    response["Cache-Control"] = "private, max-age=3600"
    response["Accept-Ranges"] = "bytes"
    return response


def serve_private_file(request, field_file):
    content_type = mimetypes.guess_type(field_file.name)[0] or "application/octet-stream"
    size = field_file.size
    match = _RANGE.match(request.headers.get("Range", "").strip())
    if not match:
        return _secure(FileResponse(field_file.open("rb"), content_type=content_type))
    first, last = match.groups()
    if first == "":  # "bytes=-500": the last 500 bytes.
        length = min(int(last or 0), size)
        start, end = size - length, size - 1
    else:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return _secure(response)
    length = end - start + 1
    response = StreamingHttpResponse(
        _iter_range(field_file.open("rb"), start, length), status=206, content_type=content_type,
    )
    response["Content-Length"] = str(length)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    return _secure(response)
