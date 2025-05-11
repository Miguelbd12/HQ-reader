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
import tempfile
import os

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

def debug_image_processing(image):
    st.subheader("🖼️ Image Processing Steps")
    
    # Convert to numpy array
    img_np = np.array(image)
    
    # Show original image
    st.image(img_np, caption="Original Image", use_column_width=True)
    
    # Grayscale conversion
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    gray_display = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    st.image(gray_display, caption="Grayscale Conversion", use_column_width=True)
    
    # Gaussian blur
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    blurred_display = cv2.cvtColor(blurred, cv2.COLOR_GRAY2RGB)
    st.image(blurred_display, caption="Gaussian Blur", use_column_width=True)
    
    # Adaptive threshold
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    thresh_display = cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB)
    st.image(thresh_display, caption="Adaptive Threshold", use_column_width=True)
    
    # Final resized image
    img_resized = cv2.resize(thresh, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    resized_display = cv2.cvtColor(img_resized, cv2.COLOR_GRAY2RGB)
    st.image(resized_display, caption="Final Processed Image (1.5x)", use_column_width=True)
    
    return Image.fromarray(img_resized)

def extract_state(text, customer):
    state = "Unknown"
    for st_code in US_STATES:
        if re.search(rf"\b{st_code}\b", customer.upper()):
            state = st_code
            break
    if state == "Unknown":
        for st_code in US_STATES:
            if re.search(rf"\b{st_code}\b", text.upper()):
                state = st_code
                break
    return state

def extract_invoice_data(text):
    # Invoice number extraction - handles both Draft Invoice # and Invoice #
    invoice_number = re.search(r"(?:Invoice\s*#|Draft Invoice\s*#)\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    
    # Date extraction - handles both EDT and CDT timezones
    date_match = re.search(
        r"(?:ORDER PLACED DATE|Date)\s*:\s*(.*?\d{1,2}:\d{2}:\d{2}\s*(?:a\.m\.|p\.m\.|AM|PM)?\s*[A-Z]{2,4})",
        text,
        re.IGNORECASE
    )
    
    # Improved total amount detection with multiple fallbacks
    total_due = "Not found"
    
    # 1. First try ORDER TOTAL (appears at bottom of invoice)
    order_total_match = re.search(
        r"ORDER TOTAL\s*:\s*([\d\.,]+)\s*US\$",
        text,
        re.IGNORECASE
    )
    
    # 2. Then try TOTAL DUE (appears at top of invoice)
    if not order_total_match:
        order_total_match = re.search(
            r"TOTAL DUE\s*:\s*([\d\.,]+)\s*US\$",
            text,
            re.IGNORECASE
        )
    
    # 3. Then look for CANNABIS > PRE-PACK FLOWER TOTAL
    if not order_total_match:
        order_total_match = re.search(
            r"CANNABIS > PRE\-PACK FLOWER\s*([\d\.,]+)\s*US\$\s*TOTAL:",
            text,
            re.IGNORECASE
        )
    
    if order_total_match:
        amount = order_total_match.group(1)
        # Handle European-style numbers (43.518,62) and American-style (43,518.62)
        if '.' in amount and ',' in amount:  # European style
            amount = amount.replace('.', '').replace(',', '.')
        elif ',' in amount:  # American style with commas
            amount = amount.replace(',', '')
        try:
            total_due = f"${float(amount):,.2f}"
        except ValueError:
            pass
    
    # Final fallback - look for amounts near total keywords
    if total_due == "Not found":
        lines = text.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ['total due', 'order total', 'amount due', 'invoice total', 'cannabis > pre-pack flower total']):
                # Check current line for amounts
                amount_match = re.search(r'([\d\.,]+)\s*US\$', line)
                if amount_match:
                    amount = amount_match.group(1)
                    if '.' in amount and ',' in amount:
                        amount = amount.replace('.', '').replace(',', '.')
                    elif ',' in amount:
                        amount = amount.replace(',', '')
                    try:
                        total_due = f"${float(amount):,.2f}"
                        break
                    except ValueError:
                        pass
                
                # Check next line if current line has no amount
                if i+1 < len(lines) and total_due == "Not found":
                    amount_match = re.search(r'([\d\.,]+)\s*US\$', lines[i+1])
                    if amount_match:
                        amount = amount_match.group(1)
                        if '.' in amount and ',' in amount:
                            amount = amount.replace('.', '').replace(',', '.')
                        elif ',' in amount:
                            amount = amount.replace(',', '')
                        try:
                            total_due = f"${float(amount):,.2f}"
                            break
                        except ValueError:
                            pass

    # Customer extraction - handles both formats
    customer_match = re.search(r"CUSTOMER[\n:]*\s*(.*?)(?:\nLICENSE|\nSHIP TO|\nBATCH|\nCONTACT)", text, re.IGNORECASE)
    customer = "Not found"
    if customer_match:
        customer = customer_match.group(1).strip()
        # Clean up customer name
        customer = re.sub(r'PAY TO THE ORDER OF.*', '', customer, flags=re.IGNORECASE)
        customer = re.sub(r'GTI.*', '', customer, flags=re.IGNORECASE)
        customer = re.sub(r'\s+', ' ', customer).strip()

    state = extract_state(text, customer)
    invoice_number = invoice_number.group(1) if invoice_number else "Not found"
    order_date = date_match.group(1).strip() if date_match else "Not found"
    
    return invoice_number, order_date, customer, state, total_due

if uploaded_file:
    st.write(f"**Uploaded File:** {uploaded_file.name}")

    try:
        # First try convert_from_bytes
        try:
            images = convert_from_bytes(uploaded_file.read(), dpi=300)
        except:
            # Fallback to temp file method if convert_from_bytes fails
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(uploaded_file.read())
                tmp.flush()
                images = convert_from_path(tmp.name, dpi=300)
                os.unlink(tmp.name)

        if images:
            # Show processing steps
            processed_image = debug_image_processing(images[0])
            
            # OCR with different configurations
            st.subheader("OCR Results")
            custom_configs = {
                "Default (PSM 6)": r'--oem 3 --psm 6',
                "Sparse Text (PSM 11)": r'--oem 3 --psm 11',
                "Single Column (PSM 4)": r'--oem 3 --psm 4'
            }
            
            best_text = ""
            for config_name, config in custom_configs.items():
                text = pytesseract.image_to_string(processed_image, config=config)
                with st.expander(f"{config_name} Results"):
                    st.text(text[:2000] + ("..." if len(text) > 2000 else ""))
                if len(text) > len(best_text):  # Simple heuristic to choose best result
                    best_text = text
            
            # Extract data from the best OCR result
            if best_text:
                invoice_number, order_date, customer, state, total_due = extract_invoice_data(best_text)

                st.subheader("🧾 Extracted Invoice Data")
                st.write(f"**Invoice Number:** {invoice_number}")
                st.write(f"**Order Placed Date:** {order_date}")
                st.write(f"**Customer:** {customer}")
                st.write(f"**State:** {state}")
                st.write(f"**Total Due:** {total_due}")

                # Create DataFrame for export
                data = {
                    "Invoice Number": [invoice_number],
                    "Order Placed Date": [order_date],
                    "Customer": [customer],
                    "State": [state],
                    "Total Due": [total_due]
                }
                df = pd.DataFrame(data)

                # Excel export
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Invoice Data')
                    writer.close()

                st.download_button(
                    label="📥 Download as Excel",
                    data=buffer.getvalue(),
                    file_name="invoice_data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("No text could be extracted from the invoice")

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        st.error("Please ensure all dependencies are installed:")
        st.code("pip install opencv-python-headless pdf2image pytesseract fuzzywuzzy pandas streamlit")























