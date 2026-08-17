# -*- coding: utf-8 -*-
"""
Created on Wed Mar  4 12:25:04 2026

@author: THYAGHARAJAN
"""

import re

def clean_text(text: str) -> str:
    """
    Basic PDF text cleaning for RAG.
    Removes URLs, repeated lines, extra whitespace, and noise.
    """

    # Remove URLs
    text = re.sub(r"http\S+", "", text)

    # Remove standalone dates like 02-03-2026
    text = re.sub(r"\b\d{2}-\d{2}-\d{4}\b", "", text)

    # Remove QR instruction lines
    text = re.sub(r"Scan the QR code.*", "", text, flags=re.IGNORECASE)

    # Remove extra spaces
    text = re.sub(r"\s+", " ", text)

    # Remove duplicate consecutive words
    words = text.split()
    cleaned_words = []
    prev_word = None
    for word in words:
        if word != prev_word:
            cleaned_words.append(word)
        prev_word = word

    return " ".join(cleaned_words).strip()