"""Bounded JSON transport; no redirects, proxy inheritance, or error-body logging."""

import socket
import time
import urllib.error
import urllib.request

from .contract import Invalid, MAX_RESPONSE, loads


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(url, data=None, headers=None, timeout=25, limit=MAX_RESPONSE):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, data=data, headers=headers or {})
    started = time.monotonic()
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise Invalid("http_error")
            chunks = []
            size = 0
            while True:
                if response.isclosed():
                    break
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise Invalid("timeout")
                # Bound the complete read, not only each individual socket read.
                response.fp.raw._sock.settimeout(remaining)
                chunk = response.read1(min(4096, limit + 1 - size))
                if not chunk:
                    if response.length not in (None, 0):
                        raise Invalid("malformed_response")
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > limit:
                    raise Invalid("response_too_large")
            return loads(b"".join(chunks))
    except Invalid:
        raise
    except urllib.error.HTTPError as error:
        error.close()
        raise Invalid("http_error") from None
    except (TimeoutError, socket.timeout):
        raise Invalid("timeout") from None
    except urllib.error.URLError as error:
        reason = "timeout" if isinstance(error.reason, TimeoutError) else "unavailable"
        raise Invalid(reason) from None
    except (ValueError, UnicodeError):
        raise Invalid("malformed_response") from None
    except Exception:
        raise Invalid("unavailable") from None
