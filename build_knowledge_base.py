import os
import hashlib
import json
from urllib.parse import urlparse
from scraper2 import ContentScraper
from fact_check import FactChecker
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm  # Optional progress bar

class KnowledgeBaseBuilder:
    def __init__(self, kb_dir="knowledge_base"):
        # Default KB folder (fallback)
        self.kb_dir = kb_dir
        os.makedirs(self.kb_dir, exist_ok=True)
        self.fact_checker = FactChecker()
        self.scraper = ContentScraper()

    def load_unique_urls(self, file_path="related_urls.txt") -> list:
        if not os.path.exists(file_path):
            print(f"[ERROR] File '{file_path}' not found.")
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            urls = {line.strip() for line in f if line.strip()}
        print(f"[INFO] Loaded {len(urls)} unique URLs from '{file_path}'")
        return list(urls)

    def _is_invalid_content(self, data: dict) -> bool:
        text = data.get("text", "").strip()
        title = data.get("title", "").strip().lower()
        generic_titles = {"", "page not found", "error", "403 forbidden","404 not found", "access denied", "page restricted"}
        error_phrases = ["access denied", "page not found", "page restricted", "browser is outdated","verify you are human", "enable javascript", "unsupported browser", "403 forbidden"]

        if not text or len(text.split()) < 30:
            return True
        if title in generic_titles:
            return True
        if any(phrase in text.lower() for phrase in error_phrases):
            return True
        return False

    def _clean_filename(self, url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.netloc.replace(".", "_")
        short_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"{domain}_{short_hash}.json"

    def _save_json(self, data: dict, filename: str, session_folder: str):
        """Save JSON into session-specific KB directory"""
        save_dir = session_folder or self.kb_dir
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved file: {path}")

    def build(self, claim_text: str, urls: list, output_dir: str = None, max_workers: int = 5):
        # Use session folder if provided
        session_folder = output_dir or self.kb_dir
        os.makedirs(session_folder, exist_ok=True)

        # Clean only JSON files in this session folder
        for filename in os.listdir(session_folder):
            if filename.endswith(".json"):
                os.remove(os.path.join(session_folder, filename))
        print(f"\n🧹 Cleared old KB files in: {session_folder}")

        print(f"\n🧠 Building knowledge base for claim: \"{claim_text}\"\n")

        def process_url(url):
            try:
                print(f"🔍 Processing: {url}")
                if "snopes.com" in url:
                    data = self.fact_checker.scrape_snopes(url)
                elif "politifact.com" in url:
                    data = self.fact_checker.scrape_politifact(url)
                else:
                    data = self.scraper.scrape_content(url)

                if self._is_invalid_content(data):
                    print(f" Skipping invalid or blocked content: {url}")
                    return

                filename = self._clean_filename(url)
                self._save_json(data, filename, session_folder)

            except Exception as e:
                print(f" ❌ Failed to process {url}: {e}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(tqdm(executor.map(process_url, urls), total=len(urls)))

        print(f"\n✅ Knowledge base built in: {session_folder}")
