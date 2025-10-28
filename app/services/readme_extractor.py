# app/services/readme_extractor.py

from typing import Optional
from bs4 import BeautifulSoup


class ReadmeExtractor:
    
    def extract_search_text(self, readme_html: str, max_words: int = 250) -> str:

        soup = BeautifulSoup(readme_html, 'html.parser')
        
        intro = self._extract_intro(soup, max_words=150)
        
        features = self._extract_features(soup, max_words=100)

        parts = []
        if intro:
            parts.append(intro)
        if features:
            parts.append(f"Key features: {features}")
        
        combined = " ".join(parts)
        
        words = combined.split()
        if len(words) > max_words:
            combined = " ".join(words[:max_words])
        
        return combined
    
    def _extract_intro(self, soup: BeautifulSoup, max_words: int) -> str:
        intro_parts = []

        for elem in soup.children:
            if not hasattr(elem, 'name'):
                continue
            
            if elem.name in ['h2', 'h3']:
                break

            if elem.name in ['p', 'div', 'span', 'h1', 'blockquote', 'ul', 'ol']:
                text = elem.get_text(separator=" ", strip=True)
                if text and len(text) > 10: 
                    intro_parts.append(text)
        
        intro_text = " ".join(intro_parts)
        
        return self._truncate_to_words(intro_text, max_words)
    
    def _extract_features(self, soup: BeautifulSoup, max_words: int) -> Optional[str]:

        feature_keywords = [
            "features",
            "why",
            "highlights",
            "what's included",
            "capabilities",
            "about"
        ]
        
        for heading in soup.find_all(['h2', 'h3', 'h4']):
            heading_text = heading.get_text().strip().lower()

            if any(keyword in heading_text for keyword in feature_keywords):
                
                content_parts = []
                for sibling in heading.find_next_siblings():
                    if sibling.name in ['h2', 'h3']:
                        break
                    
                    text = sibling.get_text(separator=" ", strip=True)
                    if text:
                        content_parts.append(text)
                
                section_text = " ".join(content_parts)
                
                if section_text:
                    return self._truncate_to_words(section_text, max_words)
        return None
    
    def _truncate_to_words(self, text: str, max_words: int) -> str:
        if not text:
            return ""
        
        words = text.split()
        if len(words) <= max_words:
            return text
        
        truncated_words = words[:max_words]
        return " ".join(truncated_words)
    
    def clean_readme_content(self, content: str) -> str:
        """Clean README content by converting literal \\n to actual newlines and removing excess whitespace."""
        if not content:
            return ""
        
        import re
        
        # Replace literal \n with actual newlines
        cleaned = content.replace('\\n', '\n')
        
        # Handle JSON-style double escaping if present
        if '\\\\n' in cleaned:
            cleaned = cleaned.replace('\\\\n', '\n')
        
        # Also handle other common escape sequences if present
        cleaned = cleaned.replace('\\t', '\t')  # tabs
        cleaned = cleaned.replace('\\r', '\r')  # carriage returns
        
        # Clean up excessive whitespace while preserving intentional formatting
        lines = cleaned.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Strip trailing spaces but preserve leading spaces for indentation
            cleaned_line = line.rstrip()
            cleaned_lines.append(cleaned_line)
        
        # Join lines and reduce excessive empty lines (more than 2 consecutive)
        result = '\n'.join(cleaned_lines)
        
        # Replace 3+ consecutive newlines with just 2
        result = re.sub(r'\n{3,}', '\n\n', result)
        
        return result.strip()

readme_extractor = ReadmeExtractor()


