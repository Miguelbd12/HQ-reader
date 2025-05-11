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
    Focuses on the region below the "Order Placed Date" to extract the total amount.
    """
    img_np = np.array(image)
    
    # Crop the image to focus on the region below the "Order Placed Date" (customizable based on the invoice layout)
    height, width = img_np.shape[:2]
    crop_top = height // 3  # Start cropping from the bottom third
    cropped_img = img_np[crop_top:height, :]  # Focus on the lower portion of the image
    
    # Pre-process the cropped portion
    gray = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
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
        customer = re.sub(r'\n+', ' ', customer_match.group(1).strip())  # Clean up newlines
        # Remove unwanted phrases
        customer = re.sub(r"PAY TO THE ORDER OF N/A", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"GTINJ PAYMENT TERMS", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"PAYMENT TERMS", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"GTI Nevada LLC . N/A", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"GTIHL", "", customer, flags=re.IGNORECASE)

    invoice_number = invoice_number.group(1) if invoice_number else "Not found"
    order_date = date_match.group(0).strip() if date_match else "Not found"
    
    # Try to extract a valid US state abbreviation from customer string
    state = "Unknown"
    for st_code in US_STATES:
        if re.search(rf"\b{st_code}\b", customer.upper()):
            state = st_code
            break

    return invoice_number, order_date, customer, state, total_due

if uploaded_file:
    st.write(f"**Uploaded File:** {uploaded_file.name}")

    try:
        pdf_bytes = uploaded_file.read()

        # Convert all pages to images
        images = convert_from_bytes(pdf_bytes)
        full_text = ""

        st.subheader("📄 Page Preview")

        # Show and process only the first page by default
        st.image(images[0], caption="Page 1", use_column_width=True)
        processed_image = process_image(images[0])
        custom_config = r'--oem 3 --psm 6'
        page_text = pytesseract.image_to_string(processed_image, config=custom_config)
        full_text += page_text + "\n\n"

        # Optional: process and preview all remaining pages
        if len(images) > 1:
            if st.checkbox("Show and OCR all pages"):
                for i, image in enumerate(images[1:], start=2):
                    st.image(image, caption=f"Page {i}", use_column_width=True)
                    processed_image = process_image(image)
                    page_text = pytesseract.image_to_string(processed_image, config=custom_config)
                    full_text += page_text + "\n\n"

        # Optional: show full OCR text
        with st.expander("📝 Show OCR Text (All Pages)"):
            st.text(full_text)

        # Extract data from combined OCR text
        invoice_number, order_date, customer, state, total_due = extract_invoice_data(full_text)

        st.subheader("🧾 Extracted Invoice Data")
        st.write(f"**Invoice Number:** {invoice_number}")
        st.write(f"**Order Placed Date:** {order_date}")
        st.write(f"**Customer:** {customer}")
        st.write(f"**State:** {state}")
        st.write(f"**Total Due:** {total_due}")

        data = {
            "Invoice Number": [invoice_number],
            "Order Placed Date": [order_date],
            "Customer": [customer],
            "State": [state],
            "Total Due": [total_due]
        }
        df = pd.DataFrame(data)

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

    except Exception as e:
        st.error(f"An error occurred: {e}")


















