import os
from typing import Tuple

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

try:
    from prometheus_client import multiprocess
except Exception:  # pragma: no cover
    multiprocess = None


def _label(value: str) -> str:
    cleaned = (value or "unknown").strip().lower()
    return cleaned[:120] if cleaned else "unknown"


SCRAPE_RUNS_TOTAL = Counter(
    "scrape_runs_total",
    "Total scrape runs by scope and status",
    labelnames=("scope", "status"),
)

SCRAPE_RUN_DURATION_SECONDS = Histogram(
    "scrape_run_duration_seconds",
    "End-to-end scrape run duration",
    labelnames=("scope", "status"),
    buckets=(0.5, 1, 2, 5, 10, 20, 40, 60, 120, 180, 300, 600),
)

SCRAPE_PROVIDER_RUNS_TOTAL = Counter(
    "scrape_provider_runs_total",
    "Provider-level scrape runs",
    labelnames=("provider", "status"),
)

SCRAPE_PROVIDER_DURATION_SECONDS = Histogram(
    "scrape_provider_duration_seconds",
    "Provider execution duration",
    labelnames=("provider", "status"),
    buckets=(0.2, 0.5, 1, 2, 5, 10, 20, 40, 60, 120, 300),
)

SCRAPE_PROVIDER_ARTICLES_TOTAL = Counter(
    "scrape_provider_articles_total",
    "Articles returned by each provider",
    labelnames=("provider",),
)

SCRAPE_HTTP_REQUESTS_TOTAL = Counter(
    "scrape_http_requests_total",
    "HTTP requests by provider/domain/status code",
    labelnames=("provider", "domain", "status_code"),
)

SCRAPE_HTTP_ERRORS_TOTAL = Counter(
    "scrape_http_errors_total",
    "HTTP errors by provider/domain/error type",
    labelnames=("provider", "domain", "error_type"),
)

SCRAPE_HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "scrape_http_request_duration_seconds",
    "HTTP request duration by provider/domain",
    labelnames=("provider", "domain"),
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 4, 6, 10, 20, 40),
)

SCRAPE_EXTRACTIONS_TOTAL = Counter(
    "scrape_extractions_total",
    "Extraction outcomes by provider/domain",
    labelnames=("provider", "domain", "result"),
)

SCRAPE_EXTRACTION_CONTENT_LENGTH = Histogram(
    "scrape_extraction_content_length",
    "Extracted content length by provider/domain",
    labelnames=("provider", "domain"),
    buckets=(0, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 20000),
)

SCRAPE_PLAYWRIGHT_FALLBACK_TOTAL = Counter(
    "scrape_playwright_fallback_total",
    "Playwright fallback usage/outcome by domain",
    labelnames=("domain", "result"),
)

SCRAPE_DUPLICATES_REMOVED_TOTAL = Counter(
    "scrape_duplicates_removed_total",
    "Duplicates removed during scraping pipeline",
    labelnames=("stage",),
)

SCRAPE_GUARDRAIL_EVENTS_TOTAL = Counter(
    "scrape_guardrail_events_total",
    "Guardrail events during scraping pipeline",
    labelnames=("guardrail", "provider", "reason"),
)


def observe_scrape_run(scope: str, status: str, duration_seconds: float) -> None:
    scope_label = _label(scope)
    status_label = _label(status)
    SCRAPE_RUNS_TOTAL.labels(scope=scope_label, status=status_label).inc()
    SCRAPE_RUN_DURATION_SECONDS.labels(scope=scope_label, status=status_label).observe(max(duration_seconds, 0.0))


def observe_provider_run(provider: str, status: str, duration_seconds: float, articles: int = 0) -> None:
    provider_label = _label(provider)
    status_label = _label(status)
    SCRAPE_PROVIDER_RUNS_TOTAL.labels(provider=provider_label, status=status_label).inc()
    SCRAPE_PROVIDER_DURATION_SECONDS.labels(provider=provider_label, status=status_label).observe(
        max(duration_seconds, 0.0)
    )
    if articles > 0:
        SCRAPE_PROVIDER_ARTICLES_TOTAL.labels(provider=provider_label).inc(articles)


def observe_http_request(provider: str, domain: str, status_code: str, duration_seconds: float) -> None:
    provider_label = _label(provider)
    domain_label = _label(domain)
    status_label = _label(str(status_code))
    SCRAPE_HTTP_REQUESTS_TOTAL.labels(
        provider=provider_label,
        domain=domain_label,
        status_code=status_label,
    ).inc()
    SCRAPE_HTTP_REQUEST_DURATION_SECONDS.labels(
        provider=provider_label,
        domain=domain_label,
    ).observe(max(duration_seconds, 0.0))


def observe_http_error(provider: str, domain: str, error_type: str) -> None:
    SCRAPE_HTTP_ERRORS_TOTAL.labels(
        provider=_label(provider),
        domain=_label(domain),
        error_type=_label(error_type),
    ).inc()


def observe_extraction(provider: str, domain: str, result: str, content_length: int = 0) -> None:
    provider_label = _label(provider)
    domain_label = _label(domain)
    result_label = _label(result)
    SCRAPE_EXTRACTIONS_TOTAL.labels(
        provider=provider_label,
        domain=domain_label,
        result=result_label,
    ).inc()
    if content_length > 0:
        SCRAPE_EXTRACTION_CONTENT_LENGTH.labels(
            provider=provider_label,
            domain=domain_label,
        ).observe(float(content_length))


def observe_playwright_fallback(domain: str, result: str) -> None:
    SCRAPE_PLAYWRIGHT_FALLBACK_TOTAL.labels(
        domain=_label(domain),
        result=_label(result),
    ).inc()


def observe_duplicates_removed(stage: str, count: int) -> None:
    if count > 0:
        SCRAPE_DUPLICATES_REMOVED_TOTAL.labels(stage=_label(stage)).inc(count)


def observe_guardrail_event(guardrail: str, provider: str, reason: str, count: int = 1) -> None:
    if count <= 0:
        return
    SCRAPE_GUARDRAIL_EVENTS_TOTAL.labels(
        guardrail=_label(guardrail),
        provider=_label(provider),
        reason=_label(reason),
    ).inc(count)


def render_metrics() -> Tuple[bytes, str]:
    """
    Render Prometheus metrics.
    Supports multiprocess mode when PROMETHEUS_MULTIPROC_DIR is configured.
    """
    multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR", "").strip()
    if multiproc_dir and multiprocess is not None:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST

    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def render_scraping_metrics() -> Tuple[bytes, str]:
    """
    Render only application scraping metrics (scrape_*), filtering out
    default runtime/process/python collector noise.
    """
    payload, content_type = render_metrics()
    lines = payload.decode("utf-8", errors="ignore").splitlines()
    filtered: list[str] = []

    for line in lines:
        if not line:
            continue
        if line.startswith("# HELP ") or line.startswith("# TYPE "):
            parts = line.split()
            if len(parts) >= 3 and parts[2].startswith("scrape_"):
                filtered.append(line)
            continue
        if line.startswith("scrape_"):
            filtered.append(line)

    body = ("\n".join(filtered) + "\n") if filtered else ""
    return body.encode("utf-8"), content_type
