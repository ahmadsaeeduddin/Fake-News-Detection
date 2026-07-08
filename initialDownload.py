import nltk
import spacy 
from spacy.cli import download


nltk.download('punkt')
nltk.download('punkt_tab')
nltk.download('wordnet')
nltk.download('omw-1.4')

download('en_core_web_md')

# Load the model after downloading
nlp = spacy.load('en_core_web_md')
print("Model loaded successfully!")