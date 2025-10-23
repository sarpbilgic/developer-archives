# app/services/readme_extractor.py

from typing import Optional
from bs4 import BeautifulSoup


class ReadmeExtractor:
    """
    Basit README text extractor.
    
    Sadece arama için gerekli kısımları çıkarır:
    - Intro (ilk H2'den önce)
    - Features (varsa Features section)
    
    Installation/Usage gibi teknik detaylar ATLANIR 
    (arama için irrelevant).
    """
    
    def extract_search_text(self, readme_html: str, max_words: int = 250) -> str:
        """
        README'den arama için optimize edilmiş text çıkarır.
        
        Returns:
            Combined intro + features text (~250 kelime)
        """
        soup = BeautifulSoup(readme_html, 'html.parser')
        
        # 1. Intro çıkar (ilk ~150 kelime)
        intro = self._extract_intro(soup, max_words=150)
        
        # 2. Features çıkar (varsa, ~100 kelime)
        features = self._extract_features(soup, max_words=100)
        
        # 3. Birleştir
        parts = []
        if intro:
            parts.append(intro)
        if features:
            parts.append(f"Key features: {features}")
        
        combined = " ".join(parts)
        
        # Safety: max_words'e truncate et
        words = combined.split()
        if len(words) > max_words:
            combined = " ".join(words[:max_words])
        
        return combined
    
    def _extract_intro(self, soup: BeautifulSoup, max_words: int) -> str:
        """
        İlk H2 heading'den ÖNCEKİ tüm text'i çıkarır.
        
        Örnek:
        ```
        # Project Title
        Description here...
        Some more text...
        ## Features          ← H2 bulundu, DUR!
        ```
        """
        intro_parts = []
        
        # Soup'un tüm child elementlerini sırayla oku
        for elem in soup.children:
            # Element değilse (string vs), atla
            if not hasattr(elem, 'name'):
                continue
            
            # İlk major heading (H2/H3) gördüğümüzde DUR!
            if elem.name in ['h2', 'h3']:
                break
            
            # Text içeren elementleri topla
            if elem.name in ['p', 'div', 'span', 'h1', 'blockquote', 'ul', 'ol']:
                text = elem.get_text(separator=" ", strip=True)
                if text and len(text) > 10:  # Çok kısa text'leri atla
                    intro_parts.append(text)
        
        intro_text = " ".join(intro_parts)
        
        # Max words'e truncate
        return self._truncate_to_words(intro_text, max_words)
    
    def _extract_features(self, soup: BeautifulSoup, max_words: int) -> Optional[str]:
        """
        "Features" heading'ini bulur ve o section'ın içeriğini çıkarır.
        
        Şu heading'leri arar:
        - ## Features
        - ## Why use this?
        - ## Highlights
        - ## What's included
        
        Örnek:
        ```
        ## Features          ← Bulundu!
        - Dark mode
        - Responsive
        - Accessible
        ## Installation      ← H2 bulundu, DUR!
        ```
        """
        # Bu keyword'lerden birini içeren heading ara
        feature_keywords = [
            "features",
            "why",
            "highlights",
            "what's included",
            "capabilities",
            "about"
        ]
        
        # Tüm H2/H3/H4 heading'leri tara
        for heading in soup.find_all(['h2', 'h3', 'h4']):
            heading_text = heading.get_text().strip().lower()
            
            # Bu heading'de feature keyword'ü var mı?
            if any(keyword in heading_text for keyword in feature_keywords):
                # ✅ BULUNDU! Şimdi bu heading'den sonraki içeriği al
                
                content_parts = []
                
                # Bu heading'in kardeş elementlerini (siblings) oku
                for sibling in heading.find_next_siblings():
                    # Başka bir major heading gördüysek DUR
                    if sibling.name in ['h2', 'h3']:
                        break
                    
                    # Text topla
                    text = sibling.get_text(separator=" ", strip=True)
                    if text:
                        content_parts.append(text)
                
                section_text = " ".join(content_parts)
                
                if section_text:
                    return self._truncate_to_words(section_text, max_words)
        
        # Features section bulunamadı
        return None
    
    def _truncate_to_words(self, text: str, max_words: int) -> str:
        """
        Text'i belirtilen kelime sayısına truncate eder.
        Kelime ortasından kesmez (word boundary'lere saygılı).
        """
        if not text:
            return ""
        
        words = text.split()
        if len(words) <= max_words:
            return text
        
        # İlk N kelimeyi al
        truncated_words = words[:max_words]
        return " ".join(truncated_words)


# Singleton instance
readme_extractor = ReadmeExtractor()


