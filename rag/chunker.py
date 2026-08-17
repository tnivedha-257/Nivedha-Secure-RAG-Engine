# -*- coding: utf-8 -*-
"""
Created on Tue Mar  3 16:41:30 2026

@author: THYAGHARAJAN

Reads PDFs from kkt_AIML_PDFs/
Chunk into fixed size segments
Return list of chunks with metadata
"""

import os
from typing import List, Dict
from pypdf import PdfReader
from docx import Document
import pandas as pd
from PIL import Image
import pytesseract
import cv2
from pytesseract import Output

from utils.text_cleanerV2 import clean_text



class DocChunker:
    """
    Handles document ingestion and text chunking.
    """

    def __init__(self, doc_folder: str, chunk_size: int = 500, overlap: int = 50):
        self.doc_folder = doc_folder
        self.chunk_size = chunk_size
        self.overlap = overlap

    # ---------------------------------------------------
    # Load and Parse Documents (PDF, DOCX, Excel, Images)
    # ---------------------------------------------------

    def load_pdfs(self) -> List[Dict]:
        """
        Reads all supported documents and returns page-level texts with metadata.
        (Method name preserved for compatibility.)
        """
        documents = []

        for filename in os.listdir(self.doc_folder):
            file_path = os.path.join(self.doc_folder, filename)
            ext = filename.lower().split(".")[-1]

            try:
                # ---------------- PDF ----------------
                if ext == "pdf":
                    reader = PdfReader(file_path)
                    for page_number, page in enumerate(reader.pages, start=1):
                        text = page.extract_text()
                        if text:
                            documents.append({
                                "text": text.strip(),
                                "source": filename,
                                "page": page_number
                            })

                # ---------------- DOCX ----------------
                elif ext == "docx":
                    doc = Document(file_path)
                    full_text = "\n".join([p.text for p in doc.paragraphs])
                    documents.append({
                        "text": full_text.strip(),
                        "source": filename,
                        "page": 1
                    })

                # ---------------- Excel ----------------
                elif ext in ["xlsx", "xls"]:
                    df = pd.read_excel(file_path)
                    documents.append({
                        "text": df.to_string(),
                        "source": filename,
                        "page": 1
                    })

                # ---------------- Image (OCR) ----------------
                elif ext in ["png", "jpg", "jpeg"]:
                
                    # Read image with OpenCV
                    img = cv2.imread(file_path)
                
                    # Detect orientation
                    osd = pytesseract.image_to_osd(img, output_type=Output.DICT)
                    angle = osd["rotate"]
                
                    if angle == 90:
                        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                    elif angle == 180:
                        img = cv2.rotate(img, cv2.ROTATE_180)
                    elif angle == 270:
                        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
                
                    # Convert to grayscale
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                
                    # Resize for better OCR
                    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                
                    # Apply threshold
                    thresh = cv2.threshold(
                        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )[1]
                
                    # OCR
                    text = pytesseract.image_to_string(thresh, config="--psm 6")
                
                    documents.append({
                        "text": text.strip(),
                        "source": filename,
                        "page": 1
                    })

            except Exception as e:
                print(f"Error processing {filename}: {e}")

        return documents

    # ---------------------------------------------------
    # Chunk Text
    # ---------------------------------------------------

    def chunk_documents(self) -> List[Dict]:
        """
        Splits document text into smaller chunks.
        Returns list of chunks with metadata.
        """
        pages = self.load_pdfs()
        chunks = []

        for page in pages:
            raw_text = page["text"]
            cleaned_text = clean_text(raw_text)

            start = 0
            while start < len(cleaned_text):
                end = start + self.chunk_size
                chunk_text = cleaned_text[start:end]

                chunks.append({
                    "text": chunk_text,
                    "source": page["source"],
                    "page": page["page"]
                })

                start += self.chunk_size - self.overlap

        return chunks