import requests
from bs4 import BeautifulSoup
import json
import re

class FactChecker:
    def __init__(self):
        pass

    def scrape_snopes(self, url):
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract title
        title_tag = soup.select_one('section.title-container h1')
        title = title_tag.text.strip() if title_tag else None

        # Extract author
        author_tag = soup.select_one('.author_name a')
        author = author_tag.text.strip() if author_tag else None

        # Extract publish date
        date_tag = soup.select_one('.publish_date')
        date = date_tag.text.strip().replace('Published', '').strip() if date_tag else None

        # Extract claim
        claim_tag = soup.select_one('#fact_check_rating_container .claim_cont')
        claim = claim_tag.text.strip() if claim_tag else None

        # Extract rating
        rating_tag = soup.select_one('.rating_title_wrap')
        rating = rating_tag.get_text(strip=True).split("About this rating")[0] if rating_tag else None

        # Extract main image URL
        image_tag = soup.select_one('img[src*="media.snopes.com"]')
        image_url = image_tag['src'] if image_tag else None

        # Extract evidence text from article content
        article = soup.select_one('article#article-content')
        evidence_text = ""
        if article:
            paragraphs = article.select('p') + article.select('blockquote p')
            evidence_text = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        
        
        # Extract sources
        sources = []
        source_container = soup.select_one('div.sources_wrapper')
        if source_container:
            source_paragraphs = source_container.select('p')
            for para in source_paragraphs:
                full_text = para.get_text(strip=True)

                # Extract the URL using regex
                match = re.search(r'https?://\S+', full_text)
                source_url = match.group(0) if match else None

                # Remove the URL from the text if it was found
                if source_url:
                    cleaned_text = full_text.replace(source_url, '').strip()
                    # Also remove trailing punctuation left behind, like extra periods
                    cleaned_text = re.sub(r'\s*\.\s*Accessed.*$', '', cleaned_text).strip()
                else:
                    cleaned_text = full_text

                sources.append({
                    "text": cleaned_text,
                    "url": source_url
                })



        # Final data object
        data = {
            "source": "Snopes",
            "title": title,
            "author": author,
            "publish_date": date,
            "claim": claim,
            "rating": rating,
            "image_url": image_url,
            "evidence_text": evidence_text,
            "sources": sources
        }

        # Save to facts.json
        with open("facts.json", "w") as f:
            json.dump(data, f, indent=4)

        return data


    def scrape_politifact(self, url):
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract claim (same as before)
        claim_tag = soup.find('div', class_='m-statement__quote')
        claim = claim_tag.get_text(strip=True) if claim_tag else None

        # Extract title (same element as claim)
        title = claim

        # Extract rating and image URL from <img class="c-image__original">
        rating_img_tag = soup.select_one('picture img[alt]')
        rating = None
        image_url = None

        if rating_img_tag:
            image_url = rating_img_tag.get('src')
            raw_rating = rating_img_tag.get('alt', '').strip()
            if raw_rating:
                rating = re.sub(r'\W+', ' ', raw_rating).title()


        # Extract author (from m-author__content)
        author_tag = soup.select_one('div.m-author__content a')
        author = author_tag.get_text(strip=True) if author_tag else None

        # Extract publish date
        date_tag = soup.find('span', class_='m-author__date')
        publish_date = date_tag.get_text(strip=True) if date_tag else None

        # Extract evidence text, including <header> headline
        evidence_parts = []

        # Add the header title, if it exists
        header_tag = soup.select_one('header h1.c-title--subline')
        if header_tag:
            header_text = header_tag.get_text(strip=True)
            evidence_parts.append(header_text)

        # Add the article body
        evidence_section = soup.find('article', class_='m-textblock')
        if evidence_section:
            paragraphs = evidence_section.find_all('p')
            for p in paragraphs:
                evidence_parts.append(p.get_text(strip=True))

        # Join everything into one evidence_text
        evidence_text = " ".join(evidence_parts)


        # Extract sources
        sources = []
        sources_section = soup.find('article', class_='m-superbox__content')
        if sources_section:
            for link in sources_section.find_all('a', href=True):
                sources.append({
                    "text": link.get_text(strip=True),
                    "url": link['href']
                })

        # Extract image URL from any <img> with .c-image__original
        image_url = rating_img_tag['src'] if rating_img_tag and 'src' in rating_img_tag.attrs else None

        # Final data object
        data = {
            "source": "PolitiFact",
            "title": title,
            "claim": claim,
            "rating": rating,
            "author": author,
            "publish_date": publish_date,
            "image_url": image_url,
            "evidence_text": evidence_text,
            "sources": sources
        }

        # Save to facts.json
        with open("facts.json", "w") as f:
            json.dump(data, f, indent=4)

        return data
    
    

# fc = FactChecker()
# url = "https://www.politifact.com/factchecks/2025/jun/24/social-media/video-of-woman-in-rainbow-hijab-in-iran-is-ai-gene/"
# result = fc.scrape_politifact(url)
# print(result)