import os
import json
import re
import time
import logging
from fpdf import FPDF
import PyPDF2
import faiss
import numpy as np
from typing import List, Tuple
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
from groq import Groq
import torch
device = "cuda" if torch.cuda.is_available() else "cpu"

# Suppress TensorFlow warnings
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
logging.getLogger('tensorflow').setLevel(logging.ERROR)

class FactCheckerPipeline:
    def __init__(self, json_folder, output_pdf_path, groq_api_key, model_name="all-MiniLM-L6-v2"):
        self.json_folder = json_folder
        self.output_pdf_path = output_pdf_path
        self.groq_api_key = groq_api_key
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        self.embedder = SentenceTransformer(model_name, device=device)
        self.dimension = self.embedder.get_sentence_embedding_dimension()
        self.index = faiss.IndexFlatL2(self.dimension)
        self.chunks = []

    # === Step 1: Merge JSON files into a PDF ===
    def merge_json_to_pdf(self):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        for filename in os.listdir(self.json_folder):
            if filename.endswith('.json'):
                file_path = os.path.join(self.json_folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    content = json.dumps(data, indent=2)
                    pdf.multi_cell(0, 10, content)
                    pdf.ln(10)

        pdf.output(self.output_pdf_path)

    # === Step 2: Extract and chunk PDF text ===
    def ingest_document(self) -> List[str]:
        with open(self.output_pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    page_text = re.sub(r'\n\s*\n', '\n\n', page_text)
                    page_text = re.sub(r'\s+', ' ', page_text)
                    text += page_text + "\n"

        if not text.strip():
            raise ValueError("Document is empty or could not be read.")

        self.chunks = self.text_splitter.split_text(text)
        print(f"Debug: Extracted {len(self.chunks)} chunks.")
        return self.chunks

    # === Step 3: Embed and index chunks with FAISS ===
    def create_embeddings(self) -> None:
        embeddings = self.embedder.encode(self.chunks, convert_to_numpy=True)
        self.index.reset()
        self.index.add(embeddings)
        print(f"Debug: FAISS index created with shape {embeddings.shape}")

    # === Step 4: Retrieve relevant chunks ===
    def retrieve_context(self, claim: str, top_k: int = 30) -> List[str]:
        query_embedding = self.embedder.encode([claim], convert_to_numpy=True)
        top_k = min(top_k, len(self.chunks))
        distances, indices = self.index.search(query_embedding, top_k)
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(self.chunks):
                results.append(self.chunks[idx])
        print(f"Debug: Retrieved {len(results)} chunks for claim.")
        return results

    # === Step 5: Use Groq for fact-checking ===
    def classify_claim_with_groq(self, claim: str, context_chunks: List[str]) -> str:
        client = Groq(api_key=self.groq_api_key)
        context = "\n".join(context_chunks)

        prompt = f"""
You are a professional fact-checking AI assisting in validating claims based on available contextual evidence.

## Task:
Given the following set of contextual statements, your job is to evaluate the veracity of a specific claim using the evidence provided.

## Claim:
"{claim}"

## Context:
{context}

## Classification Guidelines:
Classify the claim into **one** of the following categories:

1. **Supported** — The claim is backed by sufficient and credible evidence found in the context.
2. **Refuted** — The claim is directly contradicted by evidence found in the context.
3. **Not Enough Evidence** — There is insufficient or inconclusive evidence in the context to support or refute the claim.
4. **Conflicting Evidence / Cherrypicking** — There is factual evidence both supporting and refuting the claim, suggesting potential cherry-picking or inconsistent data.

## Instructions:
- Return only one of the classification labels.
- Provide a **clear and detailed justification** in **structured bullet points**.
- Each bullet point should cite or paraphrase relevant information from the provided context.
- Remain neutral and objective — do not infer or assume facts not present in the context.
"""


        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": "You are an AI assistant specialized in fact-checking."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()

    # === Run Full Pipeline ===
    def run_pipeline(self, claim: str) -> str:
        print("Running Fact-Checker Pipeline...")
        self.merge_json_to_pdf()
        self.ingest_document()
        self.create_embeddings()
        context_chunks = self.retrieve_context(claim)
        result = self.classify_claim_with_groq(claim, context_chunks)
        print("\n🧠 Groq Classification Result:\n", result)
        return result
