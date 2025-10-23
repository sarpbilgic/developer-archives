# app/services/embedding_text_builder.py

import base64
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
from datetime import datetime, timezone

class EmbeddingTextBuilder:
    """
    A specialized class responsible for constructing the optimal text block 
    for semantic embedding from raw GitHub repository data.
    """
    def __init__(self, raw_data: Dict[str, Any]):
        self.details = raw_data.get("details", {})
        self.languages = raw_data.get("languages", {})
        self.readme_raw = raw_data.get("readme_raw")
        self.cleaned_readme: Optional[str] = None

    def build(self) -> str:
        """
        Constructs and returns the final, structured text block for embedding.
        """
        # 1. Clean the README first, as it's used in multiple places
        self._clean_and_process_readme()

        # 2. Build each section of the dossier
        core_identity = self._build_core_identity()
        technical_dna = self._build_technical_dna()
        community_signals = self._build_community_signals()
        
        # 3. Assemble the final text, prioritizing the most important info
        # The order matters: from most abstract/important to most detailed.
        full_text = ". ".join(filter(None, [
            core_identity,
            community_signals,
            technical_dna,
            # Add the processed README at the end as detailed context
            f"Readme Content: {self.cleaned_readme}" if self.cleaned_readme else ""
        ]))
        
        return full_text

    def _build_core_identity(self) -> str:
        """Creates the most important summary of the project."""
        description = self.details.get("description", "")
        # The description is the single most important piece of text.
        # We repeat it to give it more "weight" in the embedding vector.
        return f"Project Description: {description}. Summary: {description}"

    def _build_technical_dna(self) -> str:
        """Creates a text block describing the technology stack."""
        primary_language = self.details.get("language")
        all_languages = list(self.languages.keys())
        topics = self.details.get("topics", [])

        parts = []
        if primary_language:
            parts.append(f"Primary Language is {primary_language}")
        if all_languages:
            parts.append(f"Other languages include: {', '.join(all_languages[:5])}") # Limit to top 5
        if topics:
            parts.append(f"Key topics and keywords are: {', '.join(topics)}")
            
        return ". ".join(parts)

    def _build_community_signals(self) -> str:
        """
        VERBALIZES numerical and boolean data to provide context that a model can understand.
        This is a more "mathematical" and accurate way of representing non-textual data.
        """
        stars = self.details.get("stargazers_count", 0)
        forks = self.details.get("forks_count", 0)
        is_archived = self.details.get("archived", False)
        pushed_at_str = self.details.get("pushed_at")
        
        parts = []
        
        # Convert star count into a categorical statement
        if stars > 50000:
            parts.append("This is an extremely popular and influential project")
        elif stars > 10000:
            parts.append("This is a very popular project")
        elif stars > 1000:
            parts.append("This is a popular project")

        # Verbalize the maintenance status
        if is_archived:
            parts.append("The project is archived and is no longer actively maintained")
        elif pushed_at_str:
            try:
                last_push = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
                days_since_push = (datetime.now(timezone.utc) - last_push).days
                if days_since_push <= 30:
                    parts.append("The project is actively maintained with recent updates")
                elif days_since_push > 365:
                    parts.append("The project has not been updated in over a year")
            except (ValueError, TypeError):
                pass # Ignore parsing errors

        return ". ".join(parts)

    def _clean_and_process_readme(self) -> None:
        """
        Decodes, cleans HTML, and truncates the README to the most essential part.
        The result is stored in self.cleaned_readme.
        """
        if not self.readme_raw or not self.readme_raw.get("content"):
            self.cleaned_readme = None
            return
        
        try:
            encoded_content = self.readme_raw["content"]
            decoded_bytes = base64.b64decode(encoded_content)
            html_content = decoded_bytes.decode("utf-8")
            
            soup = BeautifulSoup(html_content, 'html.parser')
            text = soup.get_text(separator=" ", strip=True)

            # TRUNCATION: The first ~500 words of a README are the most important.
            # This prevents long, irrelevant sections (like license text) from diluting the meaning.
            max_words = 500
            self.cleaned_readme = " ".join(text.split()[:max_words])
        except Exception as e:
            print(f"ERROR: Could not process README. Error: {e}")
            self.cleaned_readme = None