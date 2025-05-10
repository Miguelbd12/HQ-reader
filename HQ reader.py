import streamlit as st
from PyPDF2 import PdfReader
from pdf2image import convert_from_bytes
from PIL import Image
import pytesseract
import re
import pandas as pd
from io import BytesIO
import cv2
import numpy as np
from fuzzywuzzy import fuzz

st.title("📄 Invoice Extractor")
st.write("Upload an invoice PDF and extract key information.")

uploaded_file = st.file_uploader("Choose an invoice PDF", type=["pdf"])

# List of US state abbreviations
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY"
]

def process_image(image):
    """
    Pre-process the image for better OCR accuracy.
    Applies grayscale, blur, and adaptive thresholding.
    """
    img_np = np.array(image)
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )
    img_resized = cv2.resize(thresh, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    return Image.fromarray(img_resized)

def extract_invoice_data(text):
    """
    Extract relevant information from OCR'd text using regular expressions and fuzzy matching.
    """
    invoice_number = re.search(r"(?:Invoice|Bill)\s*#?\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    date_match = re.search(
        r"(May|June|July|Aug|Sep|Oct|Nov|Dec|Jan|Feb|Mar|Apr)[a-z]*\.?\s+\d{1,2},\s+\d{4}(?:\s+\d{1,2}:\d{2}:\d{2}\s*(?:a\.m\.|p\.m\.)\s*[A-Z]{2,4})?",
        text,
        re.IGNORECASE
    )
    
    # Flexible regex for "Total Due" that accounts for multiple variations of keywords
    total_due_match = re.search(r"(TOTAL DUE|AMOUNT DUE|TOTAL|AMOUNT)\s*[:\s]*\$?(\d+[\.,]?\d*)", text, re.IGNORECASE)
    
    # If we don't find a match, we can apply fuzzy matching to look for similar text
    total_due = "Not found"
    if total_due_match:
        total_due = f"${total_due_match.group(2)}"
    else:
        # Fuzzy matching on potential phrases like "Total Due", "Amount Due"
        total_due_phrases = ["TOTAL DUE", "AMOUNT DUE", "TOTAL", "AMOUNT"]
        for phrase in total_due_phrases:
            match_score = fuzz.partial_ratio(phrase.lower(), text.lower())
            if match_score > 80:  # Threshold for fuzzy matching
                total_due = f"Approx: {phrase}"  # This could be adjusted further to extract the amount
                break

    # Extract customer information while excluding unwanted phrases
    customer_match = re.search(r"CUSTOMER[\n:]*\s*(.*?)(?:LICENSE|SHIP TO)", text, re.DOTALL | re.IGNORECASE)
    customer = "Not found"
    if customer_match:
        customer = re.sub(r'\n+', ' ', customer_match.group(1).strip())_











