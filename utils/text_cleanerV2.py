# -*- coding: utf-8 -*-
"""
Created on Wed Mar  4 12:25:04 2026

@author: THYAGHARAJAN
"""

import re
import unicodedata

def clean_text(text: str) -> str:
    """
    Main cleaning pipeline.

    Order matters.
    """
    if not text:
        return ""

    text = normalize_unicode(text)
    text = remove_non_printable(text)
    text = remove_headers_footers(text)
    text = remove_page_numbers(text)
    text = remove_extra_whitespace(text)
    text = remove_duplicate_words(text)

    return text



def normalize_unicode(text: str) -> str:
    """
    Normalize unicode characters to a consistent form.
    Prevents strange PDF extraction artifacts.
    """
    return unicodedata.normalize("NFKC", text)


def remove_extra_whitespace(text: str) -> str:
    """
    Remove excessive spaces, tabs, and line breaks.
    """
    text = re.sub(r"[ \t]+", " ", text)         # collapse spaces
    text = re.sub(r"\n\s*\n+", "\n\n", text)    # max 2 newlines
    return text.strip()


def remove_page_numbers(text: str) -> str:
    """
    Remove standalone page numbers.
    Example: '12', '- 23 -', 'Page 5'
    """
    text = re.sub(r"\n\s*[-–]?\s*\d+\s*[-–]?\s*\n", "\n", text)
    text = re.sub(r"Page\s*\d+", "", text, flags=re.IGNORECASE)
    return text


def remove_headers_footers(text: str) -> str:
    """
    Remove common repeating header/footer patterns.
    Customize if needed.
    """
    patterns = [
        r"Copyright\s.*",
        r"All rights reserved.*",
        r"www\.[^\s]+",
        r"http[s]?://[^\s]+",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return text


def remove_non_printable(text: str) -> str:
    """
    Remove non-printable characters from PDF extraction.
    """
    return "".join(ch for ch in text if ch.isprintable())


def remove_duplicate_words(text: str) -> str:
    words = text.split()
    cleaned_words = []
    prev_word = None

    for word in words:
        if word != prev_word:
            cleaned_words.append(word)
        prev_word = word

    return " ".join(cleaned_words)




