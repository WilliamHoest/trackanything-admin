from urllib.parse import urlparse

import tldextract


_extractor = tldextract.TLDExtract(suffix_list_urls=None)


def _normalize_host(url_or_host: str) -> str:
    value = (url_or_host or "").strip().lower()
    if not value:
        return ""

    if "://" in value:
        value = urlparse(value).netloc.lower()

    value = value.split("@")[-1]
    value = value.split(":")[0]
    if value.startswith("www."):
        value = value[4:]
    return value


def get_etld_plus_one(url_or_host: str) -> str:
    """
    Return eTLD+1 for a URL/host (e.g. nyheder.tv2.dk -> tv2.dk).
    Falls back to normalized host if extraction cannot determine domain parts.
    """
    host = _normalize_host(url_or_host)
    if not host:
        return "unknown"

    try:
        parts = _extractor(host)
        if parts.domain and parts.suffix:
            return f"{parts.domain}.{parts.suffix}".lower()
    except Exception:
        pass

    return host
