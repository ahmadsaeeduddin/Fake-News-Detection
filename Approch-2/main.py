from email import generator
import os
import json
from dotenv import load_dotenv
from scraper2 import ContentScraper
from groq_claim import GroqClaimGenerator
from text_cleaner import TextCleaner
from query_extractor import DynamicKeyPhraseExtractor
from claim_time_normalizer import ClaimTimeNormalizer
from search_engine import WebSearcher
from build_knowledge_base import KnowledgeBaseBuilder
import time
from rag import FactCheckerPipeline

# Load API keys
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY_2")

# ANSI Colors
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"

def show(msg, style=RESET):
    print(f"{style}{msg}{RESET}")

def step_0_normalize_claim_time(claim: str):
    normalizer = ClaimTimeNormalizer(api_key=GROQ_API_KEY)
    normalized_claim = normalizer.normalize(claim)
    show(f"\n🕒 Normalized Claim: {normalized_claim}", CYAN + BOLD)
    return normalized_claim


def step_1_scrape_article(url: str, save_file="data.json"):
    show(f"\n🔍 Scraping article: {url}", CYAN + BOLD)
    scraper = ContentScraper()
    result = scraper.scrape_content(url)
    scraper.save_to_json(result, save_file)
    return result

def load_text_from_json(path="data.json"):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    title = data.get("title", "")
    text = data.get("text", "")
    return f"{title}. {text}" if title and title not in text else text

def step_2_clean_text(text):
    cleaner = TextCleaner()
    show("\n📰 Original Text:", CYAN + BOLD)
    print(text[:500] + '...\n')

    text = cleaner._remove_html_tags(text)
    text = cleaner._expand_contractions(text)
    text = cleaner._remove_urls(text)
    text = cleaner._to_lowercase(text)
    tokens = cleaner._tokenize(text)
    tokens = cleaner._lemmatize(tokens)

    clean_text = ' '.join(tokens)
    show("🧹 Final Cleaned Text:", CYAN + BOLD)
    print(clean_text[:500] + '...\n')

    return clean_text

def step_3_generate_claims(text: str):
    show("\n🧠 Generating claims from cleaned text...", CYAN + BOLD)
    claim_gen = GroqClaimGenerator(api_key=GROQ_API_KEY, model_name="llama3-8b-8192")
    claims = claim_gen.generate_claims_from_text(text, title="")
    if not claims:
        show("❌ No claims generated.", RED)
        return []
    
    # Apply quality filters
    quality_filtered_claims = claim_gen.filter_claims_by_quality(claims)
    final_claims = claim_gen.filter_similar_claims(quality_filtered_claims)
    scored_claims = claim_gen.score_claims_nlp(final_claims)

    return scored_claims

def step_4_extract_keywords(claim):
    extractor = DynamicKeyPhraseExtractor()
    keyphrases = extractor.get_meaningful_phrases(claim)
    show(f"\n🔑 Extracted keyphrases for claim:\n\"{claim}\"", CYAN + BOLD)
    for phrase, score in keyphrases:
        show(f"• {phrase} (Score: {score:.4f})", GREEN)
    return keyphrases

def step_5_search_related_links(query, input_url, save_file="related_urls.txt"):
    searcher = WebSearcher(save_file=save_file)
    duck_links = searcher.duckduckgo_search(query)
    google_links = searcher.google_search(query)
    all_links = list(set(duck_links + google_links))
    all_links = [url for url in all_links if url.strip() != input_url.strip()]

    with open(save_file, "w", encoding="utf-8") as f:
        for url in all_links:
            f.write(url + "\n")

    show(f"\n✅ Final {len(all_links)} links saved (excluding the input URL).", GREEN)

def step_6_build_knowledge_base(claim_text, url_file="related_urls.txt"):
    kb_builder = KnowledgeBaseBuilder()
    urls = kb_builder.load_unique_urls(url_file)

    if not urls:
        show("[⚠️ WARNING] No URLs found to build knowledge base.", YELLOW)
        return

    show("\n📚 Building knowledge base...", CYAN + BOLD)
    kb_builder.build(claim_text, urls)

def main():
    show('🚀 The system starts ..........', GREEN + BOLD)
    
    # === NEW: Let user choose input type ===
    show(f"\n{BOLD}Choose input type:{RESET}", CYAN)
    show("1. Paste a news article URL", CYAN)
    show("2. Enter a claim or statement to fact-check", CYAN)
    choice = input("Your choice (1/2): ").strip()

    if choice == "2":
        user_claim = input(f"\n{BOLD}Enter the claim to check: {RESET}").strip()

        # Step 0: Normalize temporal expressions
        normalized_claim = step_0_normalize_claim_time(user_claim)

        # Step 4: Extract keyphrases
        keyphrases = step_4_extract_keywords(normalized_claim)

        if keyphrases:
            top_phrase = keyphrases[0][0]
            step_5_search_related_links(top_phrase, input_url="")
            step_6_build_knowledge_base(normalized_claim)

            rag_checker = FactCheckerPipeline(
                json_folder="knowledge_base",
                output_pdf_path="knowledge_base.pdf",
                groq_api_key=GROQ_API_KEY
            )
            rag_checker.run_pipeline(normalized_claim)
        return

    elif choice != "1":
        show("❌ Invalid choice. Exiting.", RED)
        return

    # === Original article URL pipeline ===
    input_url = input(f"{BOLD}Enter the article URL: {RESET}").strip()

    # Step 1
    t1 = time.perf_counter()
    article_data = step_1_scrape_article(input_url)
    raw_text = load_text_from_json("data.json")
    t2 = time.perf_counter()
    show(f"⏱️ Time to scrape: {t2 - t1:.2f}s", YELLOW)

    # Step 2
    t3 = time.perf_counter()
    clean_text = step_2_clean_text(raw_text)
    t4 = time.perf_counter()
    show(f"⏱️ Time to clean: {t4 - t3:.2f}s", YELLOW)

    # Step 3
    t5 = time.perf_counter()
    ranked_claims = step_3_generate_claims(clean_text)
    t6 = time.perf_counter()
    show(f"⏱️ Time to generate claims: {t6 - t5:.2f}s", YELLOW)

    if not ranked_claims:
        show("❌ No valid claims found.", RED)
        return

    # Show top claims
    show("\n📊 Filtered & Ranked Claims:", CYAN + BOLD)
    for idx, (claim, score) in enumerate(ranked_claims, 1):
        show(f"{idx}. (Score: {score:.2f}) {claim}", GREEN)

    print(f"\n{BOLD}Enter the number of the claim you want to extract keyphrases for.\nOr type 'all' to extract keyphrases for all claims.{RESET}")
    user_input = input("Your choice: ").strip().lower()

    t7 = time.perf_counter()
    
    if user_input == "all":
        for idx, (claim, _) in enumerate(ranked_claims, 1):
            show(f"\n▶️ Processing claim #{idx}...", CYAN + BOLD)
            keyphrases = step_4_extract_keywords(claim)
            if keyphrases:
                top_phrase = keyphrases[0][0]
                step_5_search_related_links(top_phrase, input_url)
                step_6_build_knowledge_base(claim)

                rag_checker = ClaimFactChecker(
                    json_folder="knowledge_base",
                    pdf_path="knowledge_base.pdf",
                    groq_api_key=GROQ_API_KEY
                )
                rag_checker.run_pipeline(claim)

    elif user_input.isdigit():
        selected_index = int(user_input) - 1
        if 0 <= selected_index < len(ranked_claims):
            selected_claim = ranked_claims[selected_index][0]
            keyphrases = step_4_extract_keywords(selected_claim)
            if keyphrases:
                top_phrase = keyphrases[0][0]
                step_5_search_related_links(top_phrase, input_url)
                step_6_build_knowledge_base(selected_claim)

                rag_checker = ClaimFactChecker(
                    json_folder="knowledge_base",
                    pdf_path="knowledge_base.pdf",
                    groq_api_key=GROQ_API_KEY
                )
                rag_checker.run_pipeline(selected_claim)
        else:
            show("❌ Invalid selection. Index out of range.", RED)
    else:
        show("❌ Invalid input. Please enter a valid number or 'all'.", RED)

    t8 = time.perf_counter()
    show(f"⏱️ Time for extraction + RAG: {t8 - t7:.2f}s", YELLOW)

if __name__ == "__main__":
    start = time.time()
    main()
    end = time.time()
    print("\n" + "="*50)
    show(f"\n⏱️ Total execution time: {end - start:.2f} seconds", GREEN + BOLD)
    show("🚀 The system finished successfully!", GREEN)