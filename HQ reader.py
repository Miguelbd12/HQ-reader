import streamlit as st
import pytesseract
from pdf2image import convert_from_bytes, convert_from_path
from PIL import Image
import cv2
import numpy as np
import re
import pandas as pd
from io import BytesIO
import tempfile
import os

# Set page config
st.set_page_config(page_title="Invoice Extractor", layout="wide")

# Configure Tesseract path - IMPORTANT: Set this correctly for your system
try:
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Windows
    # pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'  # Mac/Linux
except:
    st.error("""
    ## Tesseract OCR Not Found
    
    Please install Tesseract OCR first:
    - **Windows**: Download installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
    - **Mac**: Run `brew install tesseract` in terminal
    - **Linux**: Run `sudo apt install tesseract-ocr`
    
    Then set the correct path in the code.
    """)
    st.stop()

# US states list
US_STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", 
             "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
             "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", 
             "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", 
             "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]

# Main app
st.title("📄 Invoice Extractor")
st.write("Upload PDF invoices to extract key information automatically.")

# Image processing function
def process_image(image):
    """Process image for better OCR results"""
    img_np = np.array(image)
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    img_resized = cv2.resize(thresh, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    return Image.fromarray(img_resized)

# Data extraction functions
def extract_state(text, customer):
    """Extract state from customer info"""
    for st_code in US_STATES:
        if re.search(rf"\b{st_code}\b", customer.upper()):
            return st_code
    return "Unknown"

def extract_invoice_data(text):
    """Extract key invoice data from text"""
    # Invoice number
    invoice_number = re.search(r"(?:Invoice\s*#|Draft Invoice\s*#)\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    
    # Date
    date_match = re.search(
        r"(?:ORDER PLACED DATE|Date)\s*:\s*(.*?\d{1,2}:\d{2}:\d{2}\s*(?:a\.m\.|p\.m\.|AM|PM)?\s*[A-Z]{2,4})",
        text, re.IGNORECASE
    )
    
    # Total amount (multiple patterns)
    total_due = "Not found"
    patterns = [
        r"ORDER TOTAL\s*:\s*([\d\.,]+)\s*US\$",
        r"TOTAL DUE\s*:\s*([\d\.,]+)\s*US\$",
        r"CANNABIS > PRE\-PACK FLOWER\s*([\d\.,]+)\s*US\$\s*TOTAL:"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = match.group(1)
            if '.' in amount and ',' in amount:  # European style
                amount = amount.replace('.', '').replace(',', '.')
            elif ',' in amount:  # American style
                amount = amount.replace(',', '')
            try:
                total_due = f"${float(amount):,.2f}"
                break
            except ValueError:
                continue
    
    # Customer info
    customer_match = re.search(r"CUSTOMER[\n:]*\s*(.*?)(?:\nLICENSE|\nSHIP TO|\nBATCH|\nCONTACT)", text, re.IGNORECASE)
    customer = customer_match.group(1).strip() if customer_match else "Not found"
    if customer != "Not found":
        customer = re.sub(r'PAY TO THE ORDER OF.*|GTI.*', '', customer, flags=re.IGNORECASE)
        customer = re.sub(r'\s+', ' ', customer).strip()
    
    state = extract_state(text, customer)
    
    return {
        "Invoice Number": invoice_number.group(1) if invoice_number else "Not found",
        "Order Date": date_match.group(1).strip() if date_match else "Not found",
        "Customer": customer,
        "State": state,
        "Total Due": total_due
    }

# File upload and processing
uploaded_file = st.file_uploader("Upload Invoice PDF", type=["pdf"])

if uploaded_file:
    with st.spinner("Processing invoice..."):
        try:
            # Convert PDF to image
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name
            
            images = convert_from_path(tmp_path, dpi=300)
            os.unlink(tmp_path)
            
            if images:
                # Process first page
                processed_img = process_image(images[0])
                
                # OCR with multiple configurations
                ocr_configs = [
                    ('Default', '--oem 3 --psm 6'),
                    ('Sparse Text', '--oem 3 --psm 11'),
                    ('Single Column', '--oem 3 --psm 4')
                ]
                
                best_text = ""
                for config_name, config in ocr_configs:
                    text = pytesseract.image_to_string(processed_img, config=config)
                    if len(text) > len(best_text):
                        best_text = text
                
                if best_text:
                    # Extract data
                    data = extract_invoice_data(best_text)
                    
                    # Display results
                    st.success("Invoice processed successfully!")
                    st.subheader("Extracted Data")
                    
                    cols = st.columns(2)
                    cols[0].metric("Invoice Number", data["Invoice Number"])
                    cols[1].metric("Order Date", data["Order Date"])
                    cols[0].metric("Customer", data["Customer"])
                    cols[1].metric("State", data["State"])
                    st.metric("Total Due", data["Total Due"])
                    
                    # Export to Excel
                    df = pd.DataFrame([data])
                    excel_buffer = BytesIO()
                    df.to_excel(excel_buffer, index=False)
                    
                    st.download_button(
                        label="📥 Download as Excel",
                        data=excel_buffer.getvalue(),
                        file_name="invoice_data.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.error("No text could be extracted from the invoice")
            
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            st.error("Please ensure all dependencies are installed:")
            st.code("pip install opencv-python pdf2image pytesseract pandas streamlit")
