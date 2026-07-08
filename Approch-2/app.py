from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
import time
from dotenv import load_dotenv
import threading
import uuid
from pathlib import Path
# Import your existing modules
from scraper2 import ContentScraper
from groq_claim import GroqClaimGenerator
from text_cleaner import TextCleaner
from query_extractor import DynamicKeyPhraseExtractor
from search_engine import WebSearcher
from build_knowledge_base import KnowledgeBaseBuilder
from rag import FactCheckerPipeline

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')  # Serves files from current directory
# Enable CORS for all origins (any IP/domain)
CORS(app, resources={r"/*": {"origins": ["http://149.40.228.126:5000", "https://localhost:5000"]}})

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY_1")

class FakeNewsDetectionAPI:
    def __init__(self):
        self.groq_api_key = GROQ_API_KEY
        self.results_cache = {}

    def get_unique_kb_path(self):
        thread_id = threading.get_ident()
        unique_id = uuid.uuid4().hex[:8]
        folder = f"knowledge_base/session_{thread_id}_{unique_id}"
        os.makedirs(folder, exist_ok=True)
        return folder

    def scrape_article(self, url, session_folder):
        try:
            scraper = ContentScraper()
            result = scraper.scrape_content(url)
            save_path = os.path.join(session_folder, "data.json")
            scraper.save_to_json(result, save_path)
            return result
        except Exception as e:
            raise Exception(f"Failed to scrape article: {str(e)}")

    def load_text_from_json(self, session_folder):
        path = os.path.join(session_folder, "data.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            title = data.get("title", "")
            text = data.get("text", "")
            return f"{title}. {text}" if title and title not in text else text
        except Exception as e:
            raise Exception(f"Failed to load text: {str(e)}")

    def clean_text(self, text):
        try:
            cleaner = TextCleaner()
            text = cleaner._remove_html_tags(text)
            text = cleaner._expand_contractions(text)
            text = cleaner._remove_urls(text)
            text = cleaner._to_lowercase(text)
            tokens = cleaner._tokenize(text)
            tokens = cleaner._lemmatize(tokens)
            return ' '.join(tokens)
        except Exception as e:
            raise Exception(f"Failed to clean text: {str(e)}")

    def generate_claims(self, text):
        try:
            claim_gen = GroqClaimGenerator(api_key=self.groq_api_key, model_name="llama3-8b-8192")
            claims = claim_gen.generate_claims_from_text(text, title="")

            if not claims:
                return []

            quality_filtered_claims = claim_gen.filter_claims_by_quality(claims)
            final_claims = claim_gen.filter_similar_claims(quality_filtered_claims)
            scored_claims = claim_gen.score_claims_nlp(final_claims)

            return scored_claims
        except Exception as e:
            raise Exception(f"Failed to generate claims: {str(e)}")

    def extract_keywords(self, claim):
        try:
            extractor = DynamicKeyPhraseExtractor()
            keyphrases = extractor.get_meaningful_phrases(claim)
            return keyphrases
        except Exception as e:
            raise Exception(f"Failed to extract keywords: {str(e)}")

    def search_related_links(self, query, input_url="", session_folder=None):
        try:
            save_file = os.path.join(session_folder, "related_urls.txt")
            searcher = WebSearcher(save_file=save_file)
            duck_links = searcher.duckduckgo_search(query)
            google_links = searcher.google_search(query)
            all_links = list(set(duck_links + google_links))

            if input_url:
                all_links = [url for url in all_links if url.strip() != input_url.strip()]

            with open(save_file, "w", encoding="utf-8") as f:
                for url in all_links:
                    f.write(url + "\n")

            return all_links
        except Exception as e:
            raise Exception(f"Failed to search related links: {str(e)}")

    def build_knowledge_base(self, claim_text, session_folder):
        try:
            url_file = os.path.join(session_folder, "related_urls.txt")
            kb_builder = KnowledgeBaseBuilder()
            urls = kb_builder.load_unique_urls(url_file)

            if not urls:
                return False

            kb_builder.build(claim_text, urls, output_dir=session_folder)
            return True
        except Exception as e:
            raise Exception(f"Failed to build knowledge base: {str(e)}")

    def run_fact_check(self, claim, session_folder):
        try:
            rag_checker = FactCheckerPipeline(
                json_folder=session_folder,
                output_pdf_path=os.path.join(session_folder, "knowledge_base.pdf"),
                groq_api_key=self.groq_api_key
            )
            result = rag_checker.run_pipeline(claim)
            return result
        except Exception as e:
            raise Exception(f"Failed to run fact check: {str(e)}")

    def analyze_claim_pipeline(self, claim_text):
        session_folder = self.get_unique_kb_path()
        print(f"[DEBUG] Session folder created at: {session_folder}")
        print(f"[DEBUG] Claim text received: {claim_text}")

        try:
            keyphrases = self.extract_keywords(claim_text)
            print(f"[DEBUG] Keyphrases extracted: {keyphrases}")

            if not keyphrases:
                return {"success": False, "error": "No keywords extracted"}

            top_phrase = keyphrases[0][0]
            print(f"[DEBUG] Top keyphrase for search: {top_phrase}")

            related_links = self.search_related_links(top_phrase, session_folder=session_folder)
            print(f"[DEBUG] Found {len(related_links)} related links")

            kb_built = self.build_knowledge_base(claim_text, session_folder=session_folder)
            print(f"[DEBUG] Knowledge base built: {kb_built}")

            fact_check_result = self.run_fact_check(claim_text, session_folder=session_folder)
            print(f"[DEBUG] Fact check result: {fact_check_result}")

            return {
                "success": True,
                "claim": claim_text,
                "keyphrases": keyphrases[:5],
                "sources_found": len(related_links),
                "fact_check_result": fact_check_result
            }


        except Exception as e:
            print(f"[ERROR] analyze_claim_pipeline failed: {str(e)}")
            return {"success": False, "error": str(e)}


    def analyze_url_pipeline(self, url):
        session_folder = self.get_unique_kb_path()
        print(f"[DEBUG] New session folder: {session_folder}")
        print(f"[DEBUG] Analyzing URL: {url}")

        try:
            # Step 1: Scrape article
            print("[DEBUG] Scraping article...")
            article_data = self.scrape_article(url, session_folder)
            print(f"[DEBUG] Article scraped. Title: {article_data.get('title', 'N/A')}")

            # Step 2: Load and clean text
            print("[DEBUG] Loading raw text from JSON...")
            raw_text = self.load_text_from_json(session_folder)
            print(f"[DEBUG] Raw text length: {len(raw_text)} characters")

            print("[DEBUG] Cleaning text...")
            clean_text = self.clean_text(raw_text)
            print(f"[DEBUG] Cleaned text length: {len(clean_text)} characters")

            # Step 3: Generate claims
            print("[DEBUG] Generating claims...")
            ranked_claims = self.generate_claims(clean_text)
            print(f"[DEBUG] Number of ranked claims: {len(ranked_claims)}")

            # If no claims found
            if not ranked_claims:
                print("[DEBUG] No verifiable claims found.")
                return {
                    "success": True,
                    "url": url,
                    "message": "Article processed but no verifiable claims found",
                    "claims": []
                }

            # Step 4: Process top 3 claims
            processed_claims = []
            top_claims = ranked_claims[:3]
            print(f"[DEBUG] Processing top {len(top_claims)} claims...")

            for i, (claim, score) in enumerate(top_claims):
                print(f"[DEBUG] Analyzing claim {i+1}: {claim} (score: {score})")
                claim_result = self.analyze_claim_pipeline(claim)
                print(f"[DEBUG] Claim {i+1} analysis result: {claim_result.get('verdict', 'N/A')}")

                processed_claim = {
                    "text": claim,
                    "score": score,
                    "fact_check_result": claim_result.get("fact_check_result", "") if claim_result.get("success") else claim_result.get("error", "Analysis failed")
                }

                processed_claims.append(processed_claim)

            # Step 5: Return success response
            print(f"[DEBUG] Successfully processed {len(processed_claims)} claims.")

            return {
                "success": True,
                "url": url,
                "title": article_data.get("title", "Unknown"),
                "claims": processed_claims,
                "total_claims_found": len(ranked_claims)
            }

        except Exception as e:
            print(f"[ERROR] analyze_url_pipeline failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "url": url
            }

    def extract_explanation(self, fact_check_result):
        if isinstance(fact_check_result, dict):
            return fact_check_result.get("explanation", "Comprehensive analysis completed using multiple sources.")
        elif isinstance(fact_check_result, str):
            return fact_check_result[:500] + "..." if len(fact_check_result) > 500 else fact_check_result
        return "Analysis completed using advanced fact-checking algorithms."


# Initialize the API
detection_api = FakeNewsDetectionAPI()


# STEP 5: Serve the frontend index.html
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=5)

# API ENDPOINTS
@app.route('/analyze-claim', methods=['POST'])
def analyze_claim():
    try:
        data = request.get_json()

        if not data or 'claim' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'claim' in request body"
            }), 400

        claim_text = data['claim'].strip()

        if not claim_text:
            return jsonify({
                "success": False,
                "error": "Claim text cannot be empty"
            }), 400

        if len(claim_text) < 10:
            return jsonify({
                "success": False,
                "error": "Claim text is too short for meaningful analysis"
            }), 400

        future = executor.submit(detection_api.analyze_claim_pipeline, claim_text)
        result = future.result()  # waits for the task but doesn't block other clients

        print(f"[DEBUG] Result: {result}")

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500


@app.route('/analyze-url', methods=['POST'])
def analyze_url():
    try:
        data = request.get_json()

        if not data or 'url' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'url' in request body"
            }), 400

        url = data['url'].strip()

        if not url:
            return jsonify({
                "success": False,
                "error": "URL cannot be empty"
            }), 400

        if not (url.startswith('http://') or url.startswith('https://')):
            return jsonify({
                "success": False,
                "error": "URL must start with http:// or https://"
            }), 400

        result = detection_api.analyze_url_pipeline(url)

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    try:
        health_status = {
            "status": "healthy",
            "timestamp": time.time(),
            "components": {
                "groq_api": "configured" if GROQ_API_KEY else "missing",
                "scraper": "available",
                "text_cleaner": "available",
                "search_engine": "available",
                "knowledge_base": "available",
                "rag_pipeline": "available"
            }
        }

        return jsonify(health_status), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500


if __name__ == '__main__':
    print("🚀 Starting Fake News Detection API Server...")
    print(f"🔑 GROQ API Key: {'✅ Configured' if GROQ_API_KEY else '❌ Missing'}")
    print("📡 Server will be available at: http://localhost:5000")
    print("🌐 Frontend should connect to: http://localhost:5000")
    print("\n" + "="*50)
    print("Available endpoints:")
    print("  POST /analyze-claim - Analyze a single claim")
    print("  POST /analyze-url   - Analyze an article URL")
    print("  GET  /health        - Health check")
    print("  GET  /              - Basic status")
    print("="*50 + "\n")

    app.run(
        host='0.0.0.0',  # Accessible from any device in LAN
        port=5000,
        debug=False,  # Set to True for development
        threaded=True
    )
