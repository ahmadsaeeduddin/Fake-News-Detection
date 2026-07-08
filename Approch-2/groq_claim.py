import os
import faiss
import json
import re
import string
import time
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from groq import Groq
from sklearn.metrics.pairwise import cosine_similarity
import spacy
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize

#nltk.download('punkt')

# Load .env file
load_dotenv()

class GroqClaimGenerator:
    def __init__(self, api_key, model_name="", k=3):
        self.model_name = model_name
        self.k = k
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self.client = Groq(api_key=api_key)
        self.nlp = spacy.load("en_core_web_md")  # Load once and reuse

    def preprocess_text(self, text):
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\[[^\]]*\]", "", text)
        return text.strip()

    def sentence_split_spacy(self, text):
        doc = self.nlp(text)
        return [sent.text.strip() for sent in doc.sents]

    def remove_punctuation(self, text):
        return text.translate(str.maketrans('', '', string.punctuation))

    def adaptive_chunk_text(self, text):
        # Clip text to max 8000 words
        words = word_tokenize(text)
        if len(words) > 8000:
            text = " ".join(words[:8000])
            print(" Text clipped to 8000 words.")

        sentences = self.sentence_split_spacy(text)
        total_sentences = len(sentences)

        # Define min and max chunk limits
        min_chunks = 5
        max_chunks = 12

        # Determine chunk count within range
        if total_sentences < min_chunks * 2:
            num_chunks = min_chunks
        elif total_sentences > max_chunks * 6:
            num_chunks = max_chunks
        else:
            num_chunks = min(max_chunks, max(min_chunks, total_sentences // 5))

        chunk_size = max(1, total_sentences // num_chunks)

        chunks = []
        for i in range(0, total_sentences, chunk_size):
            chunk = " ".join(sentences[i:i + chunk_size])
            chunk = self.remove_punctuation(chunk)
            chunks.append(chunk)

        print(f"🔹 Total sentences: {total_sentences} | Chunk size: {chunk_size} | Total chunks: {len(chunks)}")
        return chunks

    def build_faiss_index(self, chunks):
        print(" Indexing text...")
        embeddings = self.embedder.encode(chunks, convert_to_numpy=True)
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)
        return index, embeddings

    def retrieve_context(self, query, index, chunks, embeddings):
        query_embedding = self.embedder.encode([query], convert_to_numpy=True)
        distances, indices = index.search(query_embedding, self.k)
        return [chunks[i] for i in indices[0]]

    def generate_claim(self, context):
        prompt = f"""
Given the context below, extract one single, concise, and fact-checkable claim **as a complete sentence**.

The claim must:
- Be self-contained with essential context (who, what, when, where)
- Avoid pronouns without clear antecedents
- Be specific and verifiable
- Be between 8-20 words
- Not contain phrases like "according to" or "the article states"

Respond ONLY with the claim. Do not include any extra text.

Context:
\"\"\"{context}\"\"\"
""".strip()

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,  # Lower temperature for more focused results
            max_tokens=50
        )

        claim = response.choices[0].message.content.strip()
        
        # Enhanced post-processing
        if claim.lower().startswith(("claim:", "here is", "the claim is")):
            claim = re.sub(r"^(claim:|here is (the )?claim( in a single sentence)?[:\-–\s]*", "", claim, flags=re.IGNORECASE).strip()
        
        # Remove quotation marks if present
        claim = re.sub(r'^["\'](.*)["\']$', r'\1', claim)
        
        return claim

    def generate_claims_from_text(self, raw_text, title=""):
        text = self.preprocess_text(raw_text)
        chunks = self.adaptive_chunk_text(text)
        index, embeddings = self.build_faiss_index(chunks)

        print(f"\nGenerating claims from {len(chunks)} chunks sequentially...\n")

        claims = []
        for i, chunk in enumerate(chunks):
            context = " ".join(self.retrieve_context(chunk, index, chunks, embeddings))
            print(f"➡️ [{i + 1}/{len(chunks)}] Generating claim...")
            try:
                claim = self.generate_claim(context)
                if claim:
                    # Basic filtering before adding
                    if len(claim.split()) >= 5 and not claim.endswith('?'):
                        claims.append(claim)
            except Exception as e:
                print(f" Error generating claim for chunk {i + 1}: {e}")
                continue

        # 🏷️ Ensure title-enhanced claim is included
        if title:
            print("\n Enhancing title into a claim...")

            try:
                matched_chunk = max(chunks, key=lambda c: self.embedder.similarity(title, c))
            except Exception as e:
                print(f" Similarity matching failed, using fallback. Error: {e}")
                matched_chunk = chunks[0]

            print(f" Title: \"{title}\" ({len(title.split())} words)")
            print(f" Matched Chunk (Preview): \"{matched_chunk[:100]}...\" ({len(matched_chunk.split())} words)")

            try:
                enhanced_claim = self.generate_claim(matched_chunk)
                if enhanced_claim and enhanced_claim not in claims:
                    claims.append(enhanced_claim)
                    print(f"Title-enhanced claim added:\n→ {enhanced_claim}")
            except Exception as e:
                print(f"Error generating title-enhanced claim: {e}")

        return claims

    def filter_claims_by_quality(self, claims):
        """Filter out claims that are too vague or poorly formed"""
        print("\nFiltering low-quality claims...")
        filtered_claims = []
        
        for claim in claims:
            # Skip claims that are too short
            if len(claim.split()) < 5:
                print(f" Removed short claim: {claim}")
                continue
                
            # Skip claims with pronouns without clear references
            doc = self.nlp(claim)
            has_named_entity = any(ent.label_ in ['PERSON', 'ORG', 'GPE', 'LOC'] for ent in doc.ents)
            has_pronouns = any(token.pos_ == 'PRON' for token in doc)
            
            if has_pronouns and not has_named_entity:
                print(f" Removed vague claim (ambiguous pronouns): {claim}")
                continue
                
            # Skip claims that are questions
            if claim.strip().endswith('?'):
                print(f" Removed question-form claim: {claim}")
                continue
                
            filtered_claims.append(claim)
            
        return filtered_claims

    def filter_similar_claims(self, claims, threshold=0.88):  # Increased threshold
        print("\nFiltering similar claims...")
        if not claims:
            return []
            
        unique_claims = []
        embeddings = self.embedder.encode(claims, convert_to_numpy=True)

        for i, emb in enumerate(embeddings):
            is_duplicate = False
            
            # Compare with all previous claims
            if i > 0:
                sims = cosine_similarity([emb], embeddings[:i])[0]
                max_sim = max(sims) if len(sims) > 0 else 0
                
                if max_sim > threshold:
                    most_similar_index = sims.argmax()
                    print(f" Removed similar claim: \"{claims[i]}\"")
                    print(f"   (similar to: \"{claims[most_similar_index]}\" | similarity: {max_sim:.2f})")
                    is_duplicate = True
            
            if not is_duplicate:
                unique_claims.append(claims[i])
                
        return unique_claims
    
    def score_claims_nlp(self, claims):
        print("\n Scoring claims using NLP (Named Entity Recognition + length)...")
        scored_claims = []

        for claim in claims:
            doc = self.nlp(claim)
            num_entities = len(doc.ents)
            num_tokens = len(doc)
            score = num_entities + (0.1 * num_tokens)
            scored_claims.append((claim, score))

        return sorted(scored_claims, key=lambda x: x[1], reverse=True)


# def load_article_text(filepath="data.json"):
#     with open(filepath, "r", encoding="utf-8") as f:
#         data = json.load(f)
#     title = data.get("title", "").strip()
#     text = data.get("text", "").strip()
#     article = f"{title}. {text}" if title and title not in text else text
#     return article, title

# if __name__ == "__main__":
#     article_text, article_title = load_article_text()
#     if not article_text:
#         print(" No article text found.")
#         exit()

#     api_key = os.getenv("GROQ_API_KEY_4")
#     if not api_key:
#         print(" No API key found in .env file.")
#         exit()

#     generator = GroqClaimGenerator(api_key=api_key, model_name="llama3-8b-8192")
#     claims = generator.generate_claims_from_text(article_text, title=article_title)
    
#     # Apply quality filters
#     quality_filtered_claims = generator.filter_claims_by_quality(claims)
#     final_claims = generator.filter_similar_claims(quality_filtered_claims)
#     scored_claims = generator.score_claims_nlp(final_claims)

#     print("\n🏆 Top Factual Claims:")
#     for i, (claim, score) in enumerate(scored_claims, 1):
#         print(f"{i}. (Score: {score:.2f}) {claim}")