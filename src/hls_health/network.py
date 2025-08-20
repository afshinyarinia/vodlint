from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter, Retry


@dataclass
class HttpClient:
	timeout_seconds: float = 10.0
	retries: int = 2
	user_agent: str = "hls-health/0.1"

	def _session(self) -> requests.Session:
		session = requests.Session()
		retry = Retry(
			total=self.retries,
			backoff_factor=0.3,
			status_forcelist=(502, 503, 504),
			allowed_methods=("GET", "HEAD"),
		)
		adapter = HTTPAdapter(max_retries=retry)
		session.mount("http://", adapter)
		session.mount("https://", adapter)
		session.headers.update({"User-Agent": self.user_agent})
		return session

	def get_bytes(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
		with self._session() as s:
			resp = s.get(url, headers=headers, timeout=self.timeout_seconds)
			resp.raise_for_status()
			return resp.content
