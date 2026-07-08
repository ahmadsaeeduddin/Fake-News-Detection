import os
import re
import json
import faiss
import spacy
import numpy as np
from dotenv import load_dotenv
from groq import Groq
from textblob import TextBlob
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

# Load env vars
load_dotenv()
nlp = spacy.load("en_core_web_sm")

class GroqClaimGenerator:
    def __init__(self, api_key, model_name="llama3-8b-8192", k=3):
        api_key = os.getenv("GROQ_API_KEY_4")
        self.client = Groq(api_key=api_key)
        self.model_name = model_name
        self.k = k
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

    def preprocess_text(self, text):
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\[[^\]]*\]", "", text)
        return text.strip()

    def adaptive_chunk_text(self, text):
        words = text.split()
        total_words = len(words)
        if total_words > 10000:
            words = words[:10000]
            total_words = 10000
            print("⚠️ Trimming to first 10,000 words.")

        chunk_size = 400
        chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, total_words, chunk_size)]
        print(f"🔹 Total words used: {total_words} | Chunk size: {chunk_size} | Total chunks: {len(chunks)}")
        return chunks

    def build_faiss_index(self, chunks):
        print("📦 Indexing chunks with FAISS...")
        embeddings = self.embedder.encode(chunks, convert_to_numpy=True)
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)
        return index, embeddings

    def retrieve_context(self, query, index, chunks, embeddings):
        query_embedding = self.embedder.encode([query], convert_to_numpy=True)
        _, indices = index.search(query_embedding, self.k)
        return [chunks[i] for i in indices[0]]

    def generate_claim(self, context):
        """
        Generate a precise, short, fact-checkable claim with Groq.
        Removes filler automatically.
        """
        prompt = f"""
    Extract exactly ONE short, precise, fact-checkable claim from the context below.
    Keep it under 20 words if possible. Do not include commentary, multiple facts, or quotes.
    Do NOT write "Here is a concise..." — only output the claim sentence.

    Context:
    \"\"\"{context}\"\"\"

    Claim:
    """.strip()

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=50
        )
        raw = response.choices[0].message.content.strip()
        return self._clean_claim(raw)

    def _clean_claim(self, claim: str) -> str:
        """
        Remove any generic filler or unwanted leading text.
        """
        claim = claim.strip()
        patterns = [
            r"^Here is a concise, fact-checkable claim in one sentence[:\s]*",
            r"^Claim[:\s]*",
            r"^Claim\s*[:\-]*\s*",
        ]
        for pattern in patterns:
            claim = re.sub(pattern, '', claim, flags=re.IGNORECASE).strip()
        return claim


    def generate_claims_from_text(self, raw_text):
        text = self.preprocess_text(raw_text)
        chunks = self.adaptive_chunk_text(text)
        index, embeddings = self.build_faiss_index(chunks)

        print(f"\n🔍 Generating claims from {len(chunks)} chunks...\n")
        claims = []
        for i, chunk in enumerate(chunks):
            context = " ".join(self.retrieve_context(chunk, index, chunks, embeddings))
            print(f"➡️ [{i + 1}/{len(chunks)}] Generating claim...")
            try:
                claim = self.generate_claim(context)
                if claim:
                    claims.append(claim)
            except Exception as e:
                print(f"❌ Error: {e}")
                continue
        return claims

    def filter_similar_claims(self, claims, threshold=0.85):
        print("\n🧹 Removing duplicate/similar claims...")
        unique_claims = []
        embeddings = self.embedder.encode(claims, convert_to_numpy=True)

        for i, emb in enumerate(embeddings):
            if i == 0:
                unique_claims.append(claims[i])
                continue
            sims = cosine_similarity([emb], embeddings[:i])[0]
            if max(sims) < threshold:
                unique_claims.append(claims[i])
            else:
                print(f"⚠️ Dropped similar claim: \"{claims[i]}\" (max sim: {max(sims):.2f})")

        return unique_claims

    def score_and_filter_claims(self, claims):
        print("\n📊 Scoring and filtering claims using NLP signals...")
        scored_claims = []
        for claim in claims:
            doc = nlp(claim)
            num_entities = len(doc.ents)
            num_tokens = len(doc)
            stopwords = sum(1 for token in doc if token.is_stop)
            stopword_ratio = stopwords / num_tokens if num_tokens else 0

            polarity = abs(TextBlob(claim).sentiment.polarity)

            # Heuristics: skip very short, mostly stopwords, or purely emotional
            if num_tokens < 5 or stopword_ratio > 0.6 or polarity > 0.7:
                print(f"⏭️ Skipped: \"{claim}\" (tokens: {num_tokens}, stops: {stopword_ratio:.2f}, polarity: {polarity:.2f})")
                continue

            score = num_entities + (0.1 * num_tokens) + (1 - stopword_ratio)
            scored_claims.append((claim, score))

        return sorted(scored_claims, key=lambda x: x[1], reverse=True)


def load_article_text(filepath="data.json"):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    title = data.get("title", "").strip()
    text = data.get("text", "").strip()
    return f"{title}. {text}" if title and title not in text else text


def load_article_text(filepath="data.json"):
    """
    Loads your scraped article from a local JSON file.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    title = data.get("title", "").strip()
    text = data.get("text", "").strip()
    return f"{title}. {text}" if title and title not in text else text

def main():
    article_text = load_article_text()
    if not article_text:
        print("🚫 No article text found.")
        return

    api_key = os.getenv("GROQ_API_KEY_4")
    if not api_key:
        print("🚫 No API key found in .env file.")
        return

    generator = GroqClaimGenerator(api_key=api_key)

    print("\n🔍 Step 1: Generating raw claims from text...")
    raw_claims = generator.generate_claims_from_text(article_text)

    print("\n🧹 Step 2: Filtering similar claims...")
    filtered_claims = generator.filter_similar_claims(raw_claims)

    print("\n📊 Step 3: NLP scoring & final filtering...")
    scored_claims = generator.score_and_filter_claims(filtered_claims)

    if not scored_claims:
        print("🚫 No high-quality claims found after NLP filtering.")
        return

    print("\n🏆 Final Top Claims:")
    for i, (claim, score) in enumerate(scored_claims, 1):
        print(f"{i}. (Score: {score:.2f}) {claim}")

    # Optional: Save final claims to JSON
    output = [{"claim": claim, "score": score} for claim, score in scored_claims]
    with open("final_claims.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print("\n✅ Saved to final_claims.json")

if __name__ == "__main__":
    main()