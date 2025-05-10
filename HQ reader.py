import streamlit as st
from PyPDF2 import PdfReader
from pdf2image import convert_from_bytes
from PIL import Image, ImageEnhance
import pytesseract
import re
import pandas as pd
from io import BytesIO
import cv2
import numpy as np

st.title("📄 Invoice Extractor")
st.write("Upload an invoice PDF and extract key information.")

uploaded_file = st.file_uploader("Choose an invoice PDF", type=["pdf"])

def process_image(image):
    """
    Pre-process the image for better OCR accuracy.
    Includes resizing and thresholding.
    """
    # Convert PIL image to numpy array
    img_np = np.array(image)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    
    # Apply thresholding to binarize the image
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    
    # Resize to improve OCR accuracy
    img_resized = cv2.resize(thresh, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    
    # Convert back to PIL image
    processed_image = Image.fromarray(img_resized)
    return processed_image

def extract_invoice_data(text):
    """
    Extract relevant information from OCR'd text using regular expressions.
    """
    # Extract invoice number, order date, total amount, and customer name using regex
    invoice_number = re.search(r"(?:Invoice|Bill)\s*#?\s*(\d+)", text)
    date_match = re.search(r"ORDER PLACED DATE[\n:]*\s*(\d{1,2}/\d{1,2}/\d{4})", text)
    total_match = re.search(r"TOTAL DUE[\n:]*\s*\$?(\d+[\.,]?\d*)", text)
    customer_match = re.search(r"CUSTOMER[\n:]*\s*(.*?)(?:LICENSE|SHIP TO)", text, re.DOTALL)

    # Assign values or default to 'Not found'
    invoice_number = invoice_number.group(1) if invoice_number else "Not found"
    order_date = date_match.group(1).strip() if date_match else "Not found"
    total_due = f"${total_match.group(1)}" if total_match else "Not found"
    customer = customer_match.group(1).strip() if customer_match else "Not found"
    
    # Extract state from customer information (simple check for common states)
    state_match = re.search(r"(?:\b(?:[A-Z]{2})\b)", customer.upper())
    state = state_match.group(0) if state_match else "Unknown"

    return invoice_number, order_date, customer, state, total_due

if uploaded_file:
    # Display PDF name
    st.write(f"**Uploaded File:** {uploaded_file.name}")

    try:
        # Convert first page to image
        images = convert_from_bytes(uploaded_file.read(), first_page=1, last_page=1)
        image = images[0]
        st.image(image, caption="Invoice Preview", use_column_width=True)

        # Preprocess image for better OCR
        processed_image = process_image(image)

        # OCR extraction
        text = pytesseract.image_to_string(processed_image)

        # Extract data from OCR text
        invoice_number, order_date, customer, state, total_due = extract_invoice_data(text)

        # Display extracted data
        st.subheader("Extracted Invoice Data")
        st.write(f"**Invoice Number:** {invoice_number}")
        st.write(f"**Order Placed Date:** {order_date}")
        st.write(f"**Customer:** {customer}")
        st.write(f"**State:** {state}")
        st.write(f"**Total Amount:** {total_due}")

        # Prepare data for export
        data = {
            "Invoice Number": [invoice_number],
            "Order Placed Date": [order_date],
            "Customer": [customer],
            "State": [state],
            "Total Amount": [total_due]
        }
        df = pd.DataFrame(data)

        # Export to Excel
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Invoice Data')
            writer.close()
        
        # Download button for Excel file
        st.download_button(
            label="📥 Download as Excel",
            data=buffer,
            file_name="invoice_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"An error occurred: {e}")
