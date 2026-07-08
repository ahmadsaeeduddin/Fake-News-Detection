import re
import string
import contractions
from bs4 import BeautifulSoup
import nltk
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer

# Download required resources
# nltk.download('punkt')
# nltk.download('wordnet')
# nltk.download('omw-1.4')

class TextCleaner:
    def __init__(self, max_features=5000):
        self.lemmatizer = WordNetLemmatizer()
        self.vectorizer = TfidfVectorizer(max_features=max_features, stop_words='english')

    def clean_text(self, text):
        """Perform all cleaning steps on raw text"""
        text = self._remove_html_tags(text)
        text = self._expand_contractions(text)
        text = self._remove_urls(text)
        text = self._remove_language_noise(text)  # Add this line
        text = self._remove_non_latin(text)
        text = self._to_lowercase(text)
        tokens = self._tokenize(text)
        tokens = self._lemmatize(tokens)
        clean_text = ' '.join(tokens)
        return clean_text
    
    def _remove_language_noise(self, text):
        # Remove long lines with many languages (language clutter)
        lines = text.split('\n')
        clean_lines = []

        for line in lines:
            # Heuristic: line with >20 commas or >20 hyphens (language list indicators)
            if line.count(',') > 20 or line.count('-') > 50 or len(line) > 1000:
                continue
            clean_lines.append(line)

        return '\n'.join(clean_lines)

    def _remove_non_latin(self, text):
        return ''.join([ch if ch.isascii() else ' ' for ch in text])

    def _remove_html_tags(self, text):
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text()

    def _expand_contractions(self, text):
        return contractions.fix(text)

    def _remove_urls(self, text):
        url_pattern = re.compile(r'https?://\S+|www\.\S+')
        return url_pattern.sub('', text)

    def _to_lowercase(self, text):
        return text.lower()

    def _tokenize(self, text):
        return word_tokenize(text)

    def _lemmatize(self, tokens):
        return [self.lemmatizer.lemmatize(token) for token in tokens]

    def vectorize_text(self, clean_texts):
        """Convert cleaned text to TF-IDF vectors"""
        return self.vectorizer.fit_transform(clean_texts)

    def segment_sentences(self, text):
        """Split text into sentences"""
        text = self._remove_html_tags(text)
        text = self._expand_contractions(text)
        text = self._remove_urls(text)
        return sent_tokenize(text)

