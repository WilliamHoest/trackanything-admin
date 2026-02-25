from typing import Optional
import logging

from .config import _log

try:
    from scrapling.fetchers import AsyncStealthySession as _AsyncStealthySession
except Exception:
    _AsyncStealthySession = None


class AsyncStealthSessionManager:
    """
    Context manager der wrapper AsyncStealthySession med soft-fail semantik.
    Genbruger én persistent browser-kontekst med en tab-pool på tværs af alle
    URL'er i et provider-run — bedre Cloudflare-robusthed og lavere overhead
    end one-shot StealthyFetcher.
    """

    def __init__(
        self,
        max_pages: int = 3,
        timeout_ms: int = 30000,
        solve_cloudflare: bool = True,
        disable_resources: bool = False,
        block_webrtc: bool = True,
        scrape_run_id: Optional[str] = None,
    ) -> None:
        self._max_pages = max_pages
        self._timeout_ms = timeout_ms
        self._solve_cloudflare = solve_cloudflare
        self._disable_resources = disable_resources
        self._block_webrtc = block_webrtc
        self._scrape_run_id = scrape_run_id
        self._ready = False
        self._session = None

        if _AsyncStealthySession is not None:
            self._session = _AsyncStealthySession(
                timeout=timeout_ms,
                solve_cloudflare=solve_cloudflare,
                disable_resources=disable_resources,
                block_webrtc=block_webrtc,
                headless=True,
            )

    async def __aenter__(self) -> "AsyncStealthSessionManager":
        if self._session is None:
            _log(
                self._scrape_run_id,
                "AsyncStealthySession unavailable (scrapling not installed); skipping session.",
                logging.WARNING,
            )
            return self

        try:
            await self._session.start()
            self._ready = True
        except Exception as e:
            _log(
                self._scrape_run_id,
                f"AsyncStealthySession.start() failed; continuing without: {type(e).__name__}: {e}",
                logging.WARNING,
            )
            self._ready = False

        return self

    async def __aexit__(self, *_) -> None:
        if self._session is None:
            return
        try:
            await self._session.close()
        except Exception as e:
            _log(
                self._scrape_run_id,
                f"AsyncStealthySession.close() failed (ignored): {type(e).__name__}: {e}",
                logging.DEBUG,
            )

    async def fetch(self, url: str) -> Optional[tuple[str, str]]:
        """
        Henter URL via session-browseren.
        Returnerer (html, final_url) eller None ved fejl/tomt indhold.
        """
        if not self._ready or self._session is None:
            return None

        try:
            response = await self._session.fetch(
                url,
                timeout=self._timeout_ms,
                solve_cloudflare=self._solve_cloudflare,
            )
        except Exception as e:
            _log(
                self._scrape_run_id,
                f"AsyncStealthySession.fetch() error for {url}: {type(e).__name__}: {e}",
                logging.DEBUG,
            )
            return None

        # Udtræk HTML via attr-probing (samme mønster som _extract_html_from_scrapling_page)
        html = ""
        for attr in ("html_content", "html", "content", "body", "text"):
            value = getattr(response, attr, None)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            if isinstance(value, (bytes, bytearray)):
                try:
                    value = value.decode("utf-8", errors="ignore")
                except Exception:
                    continue
            if isinstance(value, str) and value.strip():
                html = value
                break

        if not html:
            return None

        # Udtræk final URL
        final_url = url
        for attr in ("url", "final_url", "response_url", "real_url"):
            value = getattr(response, attr, None)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            if isinstance(value, str) and value.strip():
                final_url = value
                break

        return html, final_url

    def get_pool_stats(self) -> dict:
        """Returnerer tab-pool statistik fra den underliggende session."""
        try:
            if self._session is not None and hasattr(self._session, "get_pool_stats"):
                return self._session.get_pool_stats()
        except Exception:
            pass
        return {}
