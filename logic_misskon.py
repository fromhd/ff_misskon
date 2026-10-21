import os
import re
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class LogicMissKon:
    BASE_URL = "https://misskon.us"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }

    CATEGORY_PATHS = {
        "top3": "top3",
        "top7": "top7",
        "top30": "top30",
        "top60": "top60",
    }

    @staticmethod
    def get_session():
        try:
            from .setup import P
            proxy_url = P.ModelSetting.get("proxy_url")
        except Exception:
            proxy_url = None

        proxies = {}
        if proxy_url:
            proxies = {"http": proxy_url, "https": proxy_url}

        try:
            import cloudscraper

            session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
        except Exception:
            session = requests.Session()

        if proxies:
            session.proxies.update(proxies)

        return session

    @staticmethod
    def is_supported_base_url(url):
        parsed = urlparse(url or "")
        host = parsed.netloc.lower()
        return bool(host) and ("misskon." in host or host.endswith(".misskon.com") or host.endswith(".misskon.us"))

    @staticmethod
    def discover_url(url=None):
        session = LogicMissKon.get_session()
        # 1. misskon.cc 주소 배포 페이지에서 최신 접속 주소 탐색
        candidates = []
        try:
            res = session.get("https://misskon.cc", headers=LogicMissKon.HEADERS, timeout=8)
            if res.status_code == 200:
                extracted = re.findall(r"https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", res.text)
                for u in extracted:
                    host = urlparse(u).netloc.lower()
                    if "misskon." in host and not host.endswith(".cc") and u not in candidates:
                        candidates.append(u)
        except Exception:
            pass

        fallback_candidates = ["https://misskon.us", "https://misskon.org", "https://misskon.com"]
        for fb in fallback_candidates:
            if fb not in candidates:
                candidates.append(fb)

        for candidate in candidates:
            try:
                r = session.get(candidate, headers=LogicMissKon.HEADERS, timeout=5, allow_redirects=True)
                if r.status_code == 200 and "misskon" in r.text.lower():
                    final_base = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"
                    return final_base
            except Exception:
                continue

        return LogicMissKon.BASE_URL

    @staticmethod
    def normalize_image_url(url):
        if not url:
            return ""
        url = url.replace("\\/", "/").replace("&amp;", "&").strip()
        if "," in url:
            url = url.split(",")[0].split(" ")[0]
        if url.startswith("//"):
            url = "https:" + url
        return url

    @staticmethod
    def get_list(base_url=None, page=1, search="", category=""):
        base_url = (base_url or LogicMissKon.BASE_URL).rstrip("/")
        if not LogicMissKon.is_supported_base_url(base_url):
            base_url = LogicMissKon.BASE_URL

        return LogicMissKon.parse_html_list(base_url, page, search, category)

    @staticmethod
    def parse_html_list(base_url, page=1, search="", category=""):
        base_url = base_url.rstrip("/")
        session = LogicMissKon.get_session()

        # URL 생성
        if search:
            # 신규 misskon: /albums/search?q=...&page=...
            target_url = f"{base_url}/albums/search?q={quote(search)}"
            if page > 1:
                target_url += f"&page={page}"
        else:
            # 앨범 목록: /albums?page=...
            target_url = f"{base_url}/albums"
            if page > 1:
                target_url += f"?page={page}"

        try:
            res = session.get(target_url, headers=LogicMissKon.HEADERS, timeout=15)
            if res.status_code != 200:
                try:
                    from .setup import P
                    P.logger.error(f"[MissKon] HTML List HTTP {res.status_code}: {target_url}")
                except Exception:
                    pass
                return []

            soup = BeautifulSoup(res.text, "html.parser")
            results = []
            seen = set()

            for a in soup.find_all("a"):
                href = a.get("href", "")
                if "/albums/" not in href or href.endswith("/search") or "/search?" in href:
                    continue
                full_url = urljoin(base_url, href)
                if full_url in seen:
                    continue
                seen.add(full_url)

                title_tag = a.select_one("h3") or a.select_one("h2") or a.select_one("h4")
                title = title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)

                img = a.select_one("img")
                thumb = ""
                if img:
                    thumb = img.get("src") or img.get("data-src") or ""
                thumb = LogicMissKon.normalize_image_url(urljoin(base_url, thumb))

                results.append({
                    "id": LogicMissKon._id_from_url(full_url),
                    "title": title,
                    "url": full_url,
                    "thumbnail": thumb,
                })

            return results
        except Exception as e:
            try:
                from .setup import P
                P.logger.error(f"[MissKon] HTML List Exception: {e} ({target_url})")
            except Exception:
                pass
            return []

    @staticmethod
    def get_detail(url, session=None):
        try:
            if session is None:
                session = LogicMissKon.get_session()

            soup = LogicMissKon._fetch_soup(session, url)
            if not soup:
                return None

            title_el = soup.find("h1") or soup.select_one(".entry-title, .post-title, h1")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title and soup.title:
                title = soup.title.get_text(strip=True).split(" - ")[0].split(" | ")[0]

            data = {
                "title": title or LogicMissKon._id_from_url(url),
                "images": [],
                "videos": [],
                "downloads": [],
            }

            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    full_src = urljoin(url, src)
                    if LogicMissKon._is_content_image(full_src) and full_src not in data["images"]:
                        data["images"].append(full_src)

            for iframe in soup.select("iframe"):
                src = urljoin(url, iframe.get("src", ""))
                if src and src not in data["videos"]:
                    data["videos"].append(src)

            for a in soup.find_all("a", href=True):
                href = urljoin(url, a.get("href", ""))
                if LogicMissKon._is_download_link(href):
                    if not any(row["link"] == href for row in data["downloads"]):
                        data["downloads"].append(
                            {"name": a.get_text(strip=True) or "Download Link", "link": href}
                        )

            return data
        except Exception as e:
            print(f"[MissKon] get_detail error: {type(e).__name__}: {e}")
            return None

    @staticmethod
    def _fetch_soup(session, url):
        try:
            res = session.get(url, headers=LogicMissKon.HEADERS, timeout=20)
            if res.status_code == 200:
                return BeautifulSoup(res.text, "html.parser")
            else:
                try:
                    from .setup import P
                    P.logger.error(f"[MissKon] Detail fetch HTTP {res.status_code}: {url}")
                except Exception:
                    pass
        except Exception as e:
            try:
                from .setup import P
                P.logger.error(f"[MissKon] Detail fetch exception: {e} ({url})")
            except Exception:
                pass
        return None

    @staticmethod
    def _is_content_image(url):
        lowered = url.lower()
        if not lowered.startswith(("http://", "https://")):
            return False
        if any(token in lowered for token in ["avatar", "logo", "blank", "loading", "favicon", "yandex.ru", "google"]):
            return False
        return bool(re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", lowered))

    @staticmethod
    def _is_download_link(url):
        host = urlparse(url).netloc.lower()
        if not host:
            return False
        if "misskon." in host:
            return False
        providers = [
            "mediafire",
            "mega.nz",
            "terabox",
            "pixeldrain",
            "gofile",
            "drive.google",
            "dropbox",
            "katfile",
            "rapidgator",
            "send.cm",
        ]
        return any(provider in host for provider in providers)

    @staticmethod
    def _id_from_url(url):
        path = urlparse(url).path.strip("/")
        return path.split("/")[-1] if path else url


if __name__ == "__main__":
    items = LogicMissKon.get_list(page=1)
    for item in items[:3]:
        print(item["title"], item["url"], item["thumbnail"])
