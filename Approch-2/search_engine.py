import os
from dotenv import load_dotenv
from serpapi import GoogleSearch
from ddgs import DDGS

load_dotenv()  # Load environment variables from .env file

class WebSearcher:
    def __init__(self, save_file="related_urls.txt"):
        self.save_file = save_file
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        if not self.serpapi_key:
            print("[WARNING] SERPAPI_KEY not found in environment variables.")

    def clear_results(self):
        """Clears the contents of the results file."""
        open(self.save_file, "w").close()

    def save_results(self, links, source):
        """Appends links to the results file."""
        with open(self.save_file, "a", encoding="utf-8") as f:
            for link in links:
                f.write(link + "\n")
        print(f"[{source}] Saved {len(links)} results to '{self.save_file}'")

    def google_search(self, query, num_results=15):
        """Search using Google via SerpAPI."""
        if not self.serpapi_key:
            print("[ERROR] Cannot run Google search without SERPAPI_KEY.")
            return []

        print(f"\n[GOOGLE] Searching for: \"{query}\"")
        params = {
            "q": query,
            "num": num_results,
            "api_key": self.serpapi_key
        }

        search = GoogleSearch(params)
        results = search.get_dict()
        links = []

        for result in results.get("organic_results", []):
            link = result.get("link")
            if link:
                print(f"[GOOGLE] Found: {link}")
                links.append(link)

        self.save_results(links, "GOOGLE")
        return links

    def duckduckgo_search(self, query, max_results=15):
        """Search using DuckDuckGo via duckduckgo_search library."""
        print(f"\n[DUCKDUCKGO] Searching for: \"{query}\"")
        results = []

        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    print(f"[DUCKDUCKGO] Found: {r['href']}")
                    results.append(r["href"])
        except Exception as e:
            print(f"[ERROR] DuckDuckGo search failed: {e}")
            return []

        self.save_results(results, "DUCKDUCKGO")
        return results


# def main():
#     query = input("Enter your search query: ").strip()
#     if not query:
#         print("[ERROR] Search query cannot be empty.")
#         return

#     searcher = WebSearcher()
#     searcher.clear_results()  # Optional: clear old results

#     google_links = searcher.google_search(query)
#     duck_links = searcher.duckduckgo_search(query)

#     total = len(google_links) + len(duck_links)
#     print(f"\n✅ Total {total} results saved to '{searcher.save_file}'.")

# if __name__ == "__main__":
#     main()