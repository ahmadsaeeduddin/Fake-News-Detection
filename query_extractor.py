from keybert import KeyBERT
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

class DynamicKeyPhraseExtractor:
    def __init__(self):
        self.model = KeyBERT()

    def get_meaningful_phrases(self, claim, top_n=5):
        words = claim.split()
        total_words = len(words)

        # Count number of non-stopword tokens
        meaningful_words = [w for w in words if w.lower() not in ENGLISH_STOP_WORDS]
        num_meaningful = len(meaningful_words)

        # Define dynamic n-gram range
        min_n = min(3, total_words)                # At least trigrams if possible
        max_n = min(total_words, num_meaningful)   # Max n shouldn't exceed input length

        if min_n > max_n:
            min_n = 1

        # Extract keyphrases
        keyphrases = self.model.extract_keywords(
            claim,
            keyphrase_ngram_range=(min_n, max_n),
            stop_words='english',
            top_n=top_n
        )

        return keyphrases

# if __name__ == "__main__":
#     extractor = DynamicKeyPhraseExtractor()
#     claim = input("Enter your claim: ")
#     keyphrases = extractor.get_meaningful_phrases(claim)

#     print("\nExtracted meaningful phrases:")
#     for phrase, score in keyphrases:
#         print(f"- {phrase}")