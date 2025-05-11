import streamlit as st
from PyPDF2 import PdfReader
from pdf2image import convert_from_bytes, convert_from_path
from PIL import Image
import pytesseract
import re
import pandas as pd
from io import BytesIO
import cv2
import numpy as np
import tempfile
import os

# Configure Tesseract path (UPDATE THIS)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Windows example
# pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'  # Mac/Linux

st.title("📄 Invoice Extractor (Debug Mode)")
st.write("Upload an invoice PDF to debug extraction issues.")

uploaded_file = st.file_uploader("Choose an invoice PDF", type=["pdf"])

US_STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", 
             "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
             "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", 
             "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", 
             "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]

def debug_image_processing(image):
    st.subheader("🖼️ Image Processing Steps")
    cols = st.columns(2)
    
    img_np = np.array(image)
    cols[0].image(img_np, caption="Original", use_column_width=True)
    
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    cols[1].image(gray, caption="Grayscale", use_column_width=True, cmap='gray')
    
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    cols[0].image(blurred, caption="Blurred", use_column_width=True, cmap='gray')
    
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    cols[1].image(thresh, caption="Threshold", use_column_width=True, cmap='gray')
    
    img_resized = cv2.resize(thresh, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    st.image(img_resized, caption="Final Processed (1.5x)", use_column_width=True, cmap='gray')
    
    return Image.fromarray(img_resized)

def extract_invoice_data_debug(text):
    st.subheader("🔍 Extraction Debugging")
    
    st.write("### Full OCR Text:")
    st.text(text[:2000] + ("..." if len(text) > 2000 else ""))
    
    # Invoice number
    inv_matches = list(re.finditer(r"(?:Invoice\s*#|Draft Invoice\s*#)\s*([A-Z0-9\-]+)", text, re.IGNORECASE))
    st.write(f"Invoice Number Matches ({len(inv_matches)}):")
    for i, match in enumerate(inv_matches):
        st.write(f"{i+1}. Found '{match.group(1)}' at position {match.start()}")
    
    # Date
    date_matches = list(re.finditer(
        r"(?:ORDER PLACED DATE|Date)\s*:\s*(.*?\d{1,2}:\d{2}:\d{2}\s*(?:a\.m\.|p\.m\.|AM|PM)?\s*[A-Z]{2,4})",
        text, re.IGNORECASE
    ))
    st.write(f"Date Matches ({len(date_matches)}):")
    for i, match in enumerate(date_matches):
        st.write(f"{i+1}. Found '{match.group(1)}' at position {match.start()}")
    
    # Total amounts
    total_patterns = [
        r"ORDER TOTAL\s*:\s*([\d\.,]+)\s*US\$",
        r"TOTAL DUE\s*:\s*([\d\.,]+)\s*US\$",
        r"CANNABIS > PRE\-PACK FLOWER\s*([\d\.,]+)\s*US\$\s*TOTAL:"
    ]
    
    st.write("### Total Amount Matches:")
    for pattern in total_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        st.write(f"Pattern '{pattern}': {len(matches)} matches")
        for i, match in enumerate(matches):
            st.write(f"  {i+1}. Found '{match.group(1)}' at position {match.start()}")
    
    # Customer
    cust_matches = list(re.finditer(r"CUSTOMER[\n:]*\s*(.*?)(?:\nLICENSE|\nSHIP TO|\nBATCH|\nCONTACT)", text, re.IGNORECASE))
    st.write(f"Customer Matches ({len(cust_matches)}):")
    for i, match in enumerate(cust_matches):
        st.write(f"{i+1}. Found '{match.group(1).strip()}' at position {match.start()}")
    
    # Continue with actual extraction logic...
    # [Rest of your extract_invoice_data function]

if uploaded_file:
    st.write(f"**Uploaded File:** {uploaded_file.name}")
    
    try:
        pdf_bytes = uploaded_file.read()
        
        # Try two different PDF rendering methods
        try:
            st.write("### Method 1: convert_from_bytes")
            images = convert_from_bytes(pdf_bytes, dpi=300)
            st.success("Successfully converted PDF using convert_from_bytes")
        except Exception as e:
            st.error(f"convert_from_bytes failed: {str(e)}")
            st.write("Trying fallback method with temp file...")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp.flush()
                images = convert_from_path(tmp.name, dpi=300)
                os.unlink(tmp.name)
                st.success("Successfully converted PDF using convert_from_path")
        
        if images:
            processed_image = debug_image_processing(images[0])
            
            st.subheader("🧪 OCR Results with Different Configs")
            custom_configs = {
                "PSM 6 (Default)": r'--oem 3 --psm 6',
                "PSM 11 (Sparse)": r'--oem 3 --psm 11',
                "PSM 4 (Column)": r'--oem 3 --psm 4',
                "PSM 1 (Auto)": r'--oem 3 --psm 1'
            }
            
            full_text = ""
            for name, config in custom_configs.items():
                st.write(f"**{name}**: `{config}`")
                page_text = pytesseract.image_to_string(processed_image, config=config)
                st.text(page_text[:1000] + ("..." if len(page_text) > 1000 else ""))
                full_text += f"\n\n=== {name} ===\n{page_text}"
            
            extract_invoice_data_debug(full_text)
            
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        st.exception(e)























