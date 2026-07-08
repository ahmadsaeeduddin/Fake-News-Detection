from readability import Document
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from urllib.parse import urlparse, urljoin
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import dateutil.parser
import logging
import fitz  # PyMuPDF
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContentScraper:
    def __init__(self, headless=True, wait_time=10):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.headless = headless
        self.wait_time = wait_time
        self.driver = None
        

    def _setup_driver(self):
            """Setup Selenium WebDriver for dynamic content"""
            if self.driver is None:
                chrome_options = Options()
                if self.headless:
                    chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--window-size=1920,1080")
                chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
                
                self.driver = webdriver.Chrome(options=chrome_options)
                self.driver.implicitly_wait(self.wait_time)

    
    def _close_driver(self):
        """Close Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def _identify_platform(self, url):
        """Identify the platform/website type"""
        domain = urlparse(url).netloc.lower()
        
        social_platforms = {
            'twitter.com': 'Twitter',
            'x.com': 'Twitter',
            'facebook.com': 'Facebook',
            'instagram.com': 'Instagram',
            'linkedin.com': 'LinkedIn',
            'youtube.com': 'YouTube',
            'tiktok.com': 'TikTok',
            'reddit.com': 'Reddit'
        }
        
        for platform_domain, platform_name in social_platforms.items():
            if domain == platform_domain or domain.endswith(f".{platform_domain}"):
                return platform_name, True

        return domain, False
    

    def _extract_readable_content(self, html):
        try:
            doc = Document(html)
            title = doc.short_title()
            summary_html = doc.summary()

            soup = BeautifulSoup(summary_html, 'html.parser')
            lines = []

            for elem in soup.find_all(['h1', 'h2', 'h3','h4','h5','h6' ,'p']):
                text = elem.get_text(strip=True)
                if not text:
                    continue
                if elem.name in ['h1', 'h2', 'h3','h4','h5','h6']:
                    lines.append(f"\n\n## {text}")
                else:
                    lines.append(text)

            full_text = '\n\n'.join(lines)
            return title, full_text
        except Exception as e:
            logger.warning(f"Readability failed: {e}")
            return "", ""


    
    def _extract_with_requests(self, url):
        """Try to extract content using requests + BeautifulSoup"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            logger.warning(f"Requests extraction failed: {e}")
            return None
    
    def _extract_with_selenium(self, url):
        try:
            self._setup_driver()
            self.driver.get(url)

            WebDriverWait(self.driver, self.wait_time).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            time.sleep(3)  # wait for JS content

            # Click read more buttons if present
            self._click_read_more_buttons()

            return BeautifulSoup(self.driver.page_source, 'html.parser')
        except Exception as e:
            logger.warning(f"Selenium extraction failed: {e}")
            return None



    def _click_read_more_buttons(self):
        """Click any 'Read More' buttons like Taboola, etc."""
        try:
            # Match buttons that expand content, like Taboola
            read_more_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'a.tbl-read-more-btn')
            for btn in read_more_buttons:
                if btn.is_displayed() and btn.is_enabled():
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(1)
                        btn.click()
                        time.sleep(2)  # Wait for content to load
                    except Exception as click_err:
                        logger.warning(f"Could not click read-more button: {click_err}")
        except Exception as e:
            logger.warning(f"Error while trying to click 'Read More': {e}")

    
    def _extract_meta_tags(self, soup):
        """Extract metadata from meta tags"""
        meta_data = {}
        
        # Common meta tags
        meta_mappings = {
            'og:title': 'title',
            'twitter:title': 'title',
            'og:description': 'description',
            'twitter:description': 'description',
            'og:site_name': 'site_name',
            'og:url': 'canonical_url',
            'article:published_time': 'published_time',
            'article:author': 'author',
            'og:type': 'content_type'
        }
        
        for meta_tag in soup.find_all('meta'):
            property_val = meta_tag.get('property') or meta_tag.get('name')
            content = meta_tag.get('content')
            
            if property_val and content:
                if property_val in meta_mappings:
                    meta_data[meta_mappings[property_val]] = content
        
        return meta_data
    
    def _parse_date(self, date_string):
        """Parse various date formats"""
        if not date_string:
            return None
        
        try:
            # Try parsing with dateutil (handles most formats)
            parsed_date = dateutil.parser.parse(date_string)
            return parsed_date.isoformat()
        except:
            # Try common patterns
            patterns = [
                r'\d{4}-\d{2}-\d{2}',
                r'\d{2}/\d{2}/\d{4}',
                r'\d{2}-\d{2}-\d{4}',
                r'\w+ \d{1,2}, \d{4}'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, date_string)
                if match:
                    try:
                        parsed_date = dateutil.parser.parse(match.group())
                        return parsed_date.isoformat()
                    except:
                        continue
        
        return date_string  # Return original if parsing fails


    def _extract_text_from_element(self, element):
        lines = []

        if element.name in ['h1', 'h2', 'h3', 'h4']:
            lines.append(f"\n\n## {element.get_text(strip=True)}")
        elif element.name == 'li':
            lines.append(f"- {element.get_text(strip=True)}")
        elif element.name == 'p':
            lines.append(element.get_text(strip=True))
        elif element.name in ['ul', 'ol', 'div']:
            # Recursively process only direct children
            for child in element.find_all(recursive=False):
                lines.extend(self._extract_text_from_element(child))

        return lines


    def _extract_authors(self, soup):
        """Extract author(s) from the article page."""
        author_selectors = [
            '[class*="byline"]',
            '[class*="author"]',
            '[itemprop="author"]',
            'a[href*="/author/"]',
        ]

        authors = set()

        for selector in author_selectors:
            for tag in soup.select(selector):
                text = tag.get_text(" ", strip=True)
                if not text:
                    continue

                # Remove "By" and split common connectors
                cleaned = (
                    text.replace("By ", "")
                    .replace("BY ", "")
                    .replace("by ", "")
                    .replace(" and ", ",")
                    .replace("&", ",")
                )

                for part in cleaned.split(","):
                    part = part.strip()
                    if part and len(part.split()) <= 4:  # Avoid junk strings
                        authors.add(part)

        return sorted(authors)

    def _extract_authors(self, soup):
        """Extract and clean author names."""
        author_selectors = [
            '[class*="byline"]',
            '[class*="author"]',
            '[itemprop="author"]',
            'a[href*="/author/"]',
        ]

        authors = set()

        for selector in author_selectors:
            for tag in soup.select(selector):
                text = tag.get_text(" ", strip=True)
                if not text:
                    continue

                cleaned = (
                    text.replace("By ", "")
                    .replace("BY ", "")
                    .replace("by ", "")
                    .replace(" and ", ",")
                    .replace("&", ",")
                )

                for part in cleaned.split(","):
                    part = part.strip()
                    if part and len(part.split()) <= 4:
                        authors.add(part.title())

        return sorted(authors)


    def _extract_article_content(self, soup, platform):
        """Extract structured article content without duplication, handling nested structures."""
        # --- inside _extract_article_content ---------------------------------
        content_selectors = [
            '[itemprop="articleBody"]',
            '[class*="article-content"]',
            '[class*="article-body"]',
            '[class*="story-body"]',
            '[class*="story-content"]',
            '[id^="story-content-"]',
            '[id^="article-content"]',
            '[class*="entryContent"]',
            '[class*="abstract"]',
            '[class*="container"]',
            '[id^="bodyContent"]',
            '[class*="story-section"]',
            '[class*="post-content"]',
            '[class*="wysiwyg"]',
            '[class*="primary"]',
            '[class*="article-body__content__17Yit"]'
            '[class*="responsiveSkin ifp-doc-type-oxencycl-entry"]',
            '[class*="text-component"]',
            '[class*="entry-content"]',
            '[class*="e-tab-content tab-content"]'
            '[class*="e-content-block"]'
            '[class*="elementor-post-content"]',      # WordPress/Elementor
            '[class*="elementor-widget-container"]',  # ← add this
            '[class*="elementor-element elementor-element-d72ee69 single-post-paragraph elementor-widget elementor-widget-text-editor"]',
            'article',
            'main'
        ]

        best_block = None
        max_score = 0

        for selector in content_selectors:
            for element in soup.select(selector):
                for tag in element(['script', 'style', 'nav', 'footer', 'aside', 'form', 'iframe', '.adsbygoogle']):
                    tag.decompose()

                score = len(element.find_all('p')) + len(element.find_all(['h2', 'h3', 'li']))
                if score > max_score:
                    best_block = element
                    max_score = score

        if not best_block:
            return ""

        lines = []
        processed = set()

        for tag in best_block.find_all(['h1', 'h2', 'h3', 'li', 'p', 'ul', 'ol'], recursive=True):
            text = tag.get_text(strip=True)
            if text and text not in processed:
                if tag.name in ['h1', 'h2', 'h3']:
                    lines.append(f"\n\n## {text}")
                elif tag.name == 'li':
                    lines.append(f"- {text}")
                else:
                    lines.append(text)
                processed.add(text)

        return '\n'.join(lines)

    def _extract_tweet_images(self, soup):
        """Extract images from a tweet card on Twitter/X."""
        images = {}
        count = 1

        # Find <img> tags inside tweet containers
        for img in soup.select('[data-testid="tweetPhoto"] img'):
            src = img.get('src')
            if src:
                images[f'image{count}'] = src
                count += 1

        # Fallback: background-image from inline styles
        for div in soup.select('[data-testid="tweetPhoto"] div[style]'):
            style = div.get('style', '')
            if 'background-image' in style:
                match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                if match:
                    images[f'image{count}'] = match.group(1)
                    count += 1
        return images

    def _extract_twitter_content(self, soup):
        """Extract Twitter-specific content"""
        data = {}
        
        # Twitter selectors (may need updates as Twitter changes)
        tweet_selectors = [
            '[data-testid="tweetText"]',
            '.tweet-text',
            '[data-testid="tweet"]'
        ]
        
        for selector in tweet_selectors:
            elements = soup.select(selector)
            if elements:
                data['text'] = ' '.join([elem.get_text(strip=True) for elem in elements])
                break
        
        # Extract author
        author_selectors = [
            '[data-testid="User-Name"]',
            '.username',
            '.fullname'
        ]
        
        for selector in author_selectors:
            element = soup.select_one(selector)
            if element:
                data['author'] = element.get_text(strip=True)
                break
        
        # Extract images
        data['images'] = self._extract_tweet_images(soup)
        return data

    def _extract_facebook_content(self, soup):
        """Extract Facebook-specific content"""
        data = {}
        
        # Facebook post content
        post_selectors = [
            '[data-ad-preview="message"]',
            '.userContent',
            '[data-testid="post_message"]'
        ]
        
        for selector in post_selectors:
            element = soup.select_one(selector)
            if element:
                data['text'] = element.get_text(strip=True)
                break
        
        # Extract images
        data['images'] = self._extract_images(soup,self.driver.current_url,
            [
            'img[src*="fbcdn.net"]',
            '.spotlight img',
            '[data-testid="photo"] img',
            '.userContentWrapper img',
            'img[alt*="Photo"]'
        ])
        
        return data
    
    from urllib.parse import urljoin, urlparse

    def _extract_images(self, soup, page_url, specific_selectors=None):
        """Extract and normalize all image URLs from the page"""
        
        if not soup:
            return {}
        
        
        images = {}
        image_urls = set()  # Avoid duplicates

        # Try specific selectors first
        if specific_selectors:
            for selector in specific_selectors:
                imgs = soup.select(selector)
                for img in imgs:
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                    if src and self._is_valid_image_url(src):
                        image_urls.add(src)

        # Fallback to general image extraction
        if not image_urls:
            all_imgs = soup.find_all('img')
            for img in all_imgs:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src and self._is_valid_image_url(src):
                    # Skip very small UI images
                    width = img.get('width')
                    height = img.get('height')
                    if width and height:
                        try:
                            if int(width) < 50 or int(height) < 50:
                                continue
                        except (ValueError, TypeError):
                            pass
                    image_urls.add(src)

        # Normalize and assign image URLs
        for i, src in enumerate(sorted(image_urls), 1):
            # Normalize using page_url
            full_url = urljoin(page_url, src)
            images[f'image{i}'] = full_url

        return images

    
    def _is_valid_image_url(self, url):
        """Check if URL is a valid image URL"""
        if not url or url == '#':
            return False
        
        # Skip base64 encoded images (too long for practical use)
        if url.startswith('data:image'):
            return False
        
        # Skip obvious non-image URLs
        skip_patterns = [
            'logo', 'icon', 'avatar', 'profile',
            'ads', 'tracking', 'pixel',
            '.svg', 'placeholder'
        ]
        
        url_lower = url.lower()
        for pattern in skip_patterns:
            if pattern in url_lower and any(ext in url_lower for ext in ['.gif', '.png', '.jpg', '.jpeg']):
                # Only skip if it's clearly a small UI element
                if any(size in url_lower for size in ['16x16', '32x32', '24x24', 'small', 'tiny']):
                    return False
        
        # Accept common image extensions or social media image patterns
        valid_patterns = [
            '.jpg', '.jpeg', '.png', '.gif', '.webp',
            'pbs.twimg.com', 'fbcdn.net', 'imgur.com',
            'media', 'photo', 'image'
        ]
        
        return any(pattern in url_lower for pattern in valid_patterns)
    
    def _extract_reddit_content(self, soup):
        """Extract Reddit-specific content"""
        data = {}

        def safe_get(selector_list, attr=None, text=True):
            for selector in selector_list:
                element = soup.select_one(selector)
                if element:
                    if attr:
                        value = element.get(attr)
                        if value:
                            return value.strip()
                    elif text:
                        return element.get_text(strip=True)
            return ''

        # Reddit post title from new Reddit format (shreddit-title tag)
        data['title'] = safe_get(['shreddit-title'])

        # Reddit post text (if available)
        data['text'] = safe_get([
            '[data-test-id="post-content"] div[class*="text"]',
            '.Post div[class*="text"]',
            '[data-click-id="text"] div',
            'div[class*="usertext-body"]',
            'shreddit-post[post-title]'  # Custom attribute
        ], attr='post-title', text=False)

        # Reddit author (from custom attribute)
        data['author'] = safe_get([
            'shreddit-post'
        ], attr='author', text=False)

        # Subreddit name
        data['subreddit'] = safe_get([
            'shreddit-post'
        ], attr='subreddit-name', text=False)

        # Extract Reddit images (thumbnails etc.)
        

        return data

    

    def _extract_pdf_content(self, url):
        logger.info(f"Downloading PDF: {url}")
        response = self.session.get(url)
        response.raise_for_status()

        with open("temp.pdf", "wb") as f:
            f.write(response.content)

        text = ""
        doc = fitz.open("temp.pdf")
        for page in doc:
            text += page.get_text()
        doc.close()
        os.remove("temp.pdf")

        return {
            'url': url,
            'platform': urlparse(url).netloc,
            'is_social_media': False,
            'title': "",
            'text': text.strip(),
            'author': "",
            'publisher': urlparse(url).netloc,
            'published_date': None,
            'site_name': urlparse(url).netloc,
            'images': {}
        }

    def scrape_content(self, url):
        """Main scraping function"""
        logger.info(f"Starting to scrape: {url}")
        
        try:
            head = self.session.head(url, allow_redirects=True, timeout=10)
            content_type = head.headers.get('Content-Type', '').lower()
            if content_type.startswith('application/pdf') or url.lower().endswith('.pdf'):
                return self._extract_pdf_content(url)
        except Exception as e:
            logger.warning(f"Failed to check content type: {e}")

        # Identify platform
        platform, is_social = self._identify_platform(url)
        
        # Try requests first, then Selenium if needed
        soup = self._extract_with_requests(url)
        
        if not soup or is_social:
            logger.info("Using Selenium for dynamic content extraction")
            soup = self._extract_with_selenium(url)
        
        if not soup:
            raise Exception("Failed to extract content from URL")
        
        # Extract meta data
        meta_data = self._extract_meta_tags(soup)



        # Initialize result structure
        result = {
            'url': url,
            'platform': platform,
            'is_social_media': is_social,
            'title': '',
            'text': '',
            'author': '',
            'publisher': '',
            'published_date': None,
            'site_name': platform,
            'images': {}
        }
        
        # Extract title
        title_sources = [
            meta_data.get('title'),
            soup.find('title').get_text(strip=True) if soup.find('title') else None,
            soup.find('h1').get_text(strip=True) if soup.find('h1') else None
        ]
        
        for title_source in title_sources:
            if title_source and title_source.strip():
                result['title'] = title_source.strip()
                break
        
        # Platform-specific extraction
        if platform == 'Twitter':
            twitter_data = self._extract_twitter_content(soup)
            result.update(twitter_data)
        elif platform == 'Facebook':
            facebook_data = self._extract_facebook_content(soup)
            result.update(facebook_data)
        elif platform == 'Reddit':
            reddit_data = self._extract_reddit_content(soup)
            result.update(reddit_data)
        else:
            # Generic article extraction
            result['text'] = self._extract_article_content(soup, platform)
            result['author'] = ', '.join(self._extract_authors(soup))
            if not result['text'] or len(result['text']) < 200:
                title, text = self._extract_readable_content(str(soup))
                if title and not result['title']:
                    result['title'] = title
                if text:
                    result['text'] = text

            # Extract images for articles
            result['images'] = self._extract_images(soup, url,[
                'img[src*="cdn"]',
                'figure img',
                '.featured-image img',
                '.post-image img',
                'article img'
            ])
        
        
        # For non-social media, try to find publisher
        if not is_social:
            result['publisher'] = meta_data.get('site_name') or platform
        
        # Extract date
        date_sources = [
            meta_data.get('published_time'),
            soup.select_one('time')['datetime'] if soup.select_one('time') and soup.select_one('time').get('datetime') else None,
            soup.select_one('.date, .publish-date, .post-date').get_text(strip=True) if soup.select_one('.date, .publish-date, .post-date') else None
        ]
        
        for date_source in date_sources:
            if date_source:
                parsed_date = self._parse_date(date_source)
                if parsed_date:
                    result['published_date'] = parsed_date
                    break
        
        # Clean up driver
        self._close_driver()
        
        return result
    
    def save_to_json(self, data, filename=None):
        """Save scraped data to JSON file"""
        if filename is None:
            filename = f"data.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Data saved to {filename}")
        return filename

def scrape_url(url, output_file=None):
    """Convenience function to scrape a single URL"""
    scraper = ContentScraper()
    try:
        result = scraper.scrape_content(url)
        filename = scraper.save_to_json(result, output_file)
        return result, filename
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        raise


#Example usage
if __name__ == "__main__":
    # Ask for user input
    url = input("Please enter a URL to scrape: ")
    
    scraper = ContentScraper()
    
    try:
        print(f"\nScraping: {url}")
        result = scraper.scrape_content(url)
        
        # Print summary
        print(f"Platform: {result['platform']}")
        print(f"Title: {result['title'][:100]}...")
        print(f"Text length: {len(result['text'])} characters")
        print(f"Author: {result['author']}")
        print(f"Published: {result['published_date']}")
        
        # Save to JSON
        scraper.save_to_json(result)
        
    except Exception as e:
        print(f"Error: {e}")

