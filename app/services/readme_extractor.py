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
        """Clean README content by removing HTML tags and converting to clean text."""
        if not content:
            return ""
        
        import re
        from bs4 import BeautifulSoup
        
        cleaned = content.replace('\\n', '\n')
        
        if '\\\\n' in cleaned:
            cleaned = cleaned.replace('\\\\n', '\n')
        
        if '<' in cleaned and '>' in cleaned:

            soup = BeautifulSoup(cleaned, 'html.parser')

            for script in soup(["script", "style"]):
                script.decompose()
            
            text = soup.get_text(separator='\n', strip=True)
            
            lines = text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                line = line.strip()
                if line:
                    cleaned_lines.append(line)
            
            result = '\n'.join(cleaned_lines)
            
        else:
            lines = cleaned.split('\n')
            cleaned_lines = []
            
            for line in lines:
                cleaned_line = line.rstrip()
                cleaned_lines.append(cleaned_line)
            
            result = '\n'.join(cleaned_lines)
        

        result = re.sub(r'\n{3,}', '\n\n', result)
  
        result = result.replace('\\t', '\t')  
        result = result.replace('\\r', '\r')  
        
        return result.strip()

readme_extractor = ReadmeExtractor()


