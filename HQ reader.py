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
    invoice_number = re.search(r"(?:Invoice\s*(?:No\.?|#)?|Bill\s*#?)\s*[:\-]?\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    
    date_match = re.search(
        r"(Abr\.|May|June|July|Aug|Sep|Oct|Nov|Dec|Jan|Feb|Mar|Apr)[a-z]*\.?\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}:\d{2}\s*(a\.m\.|p\.m\.)",
        text,
        re.IGNORECASE
    )
    
    # Updated regex for Total Due to match the format "1.400,00 uss"
    total_due_match = re.search(r"(\d{1,3}(?:[.,]?\d{3})*(?:[.,]\d{2})?)\s*uss", text, re.IGNORECASE)
    
    total_due = "Not found"
    if total_due_match:
        # Clean the total amount by removing "uss" and reformatting the number
        total_amount = total_due_match.group(1)  # "1.400,00"
        
        # Remove the periods (thousands separator) and replace the comma with a dot for decimal separator
        total_amount = total_amount.replace(".", "")  # Remove thousands separator
        total_amount = total_amount.replace(",", ".")  # Replace the comma with a dot for decimal

        # Format the amount to include a comma as a thousands separator and ensure two decimal places
        total_due = "{:,.2f}".format(float(total_amount))  # Convert it to float and format with commas

    else:
        total_due_phrases = ["TOTAL DUE", "AMOUNT DUE", "TOTAL", "AMOUNT", "TOTAL INVOICE", "BALANCE DUE", "OUTSTANDING"]
        lines = text.split("\n")
        for line in lines:
            for phrase in total_due_phrases:
                if fuzz.partial_ratio(phrase.lower(), line.lower()) > 85:
                    amount = re.search(r"\$?\s?(\d{1,3}(?:[.,]?\d{3})*(?:[.,]\d{2})?)", line)
                    if amount:
                        total_due = f"${amount.group(1)}"
                        break
            if total_due != "Not found":
                break

    customer_match = re.search(r"CUSTOMER[\n:]*\s*(.*?)(?:LICENSE|SHIP TO)", text, re.DOTALL | re.IGNORECASE)
    customer = "Not found"
    if customer_match:
        customer = re.sub(r'\n+', ' ', customer_match.group(1).strip())
        customer = re.sub(r"PAY TO THE ORDER OF N/A", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"GTINJ PAYMENT TERMS", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"PAYMENT TERMS", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"GTHL", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"GTI Nevada LLC\s*\.\s*N/A", "", customer, flags=re.IGNORECASE)
        customer = re.sub(r"GTIHL", "", customer, flags=re.IGNORECASE)

    st.write(f"**Raw Customer Data:** {customer}")

    state = extract_state(text, customer)
    invoice_number = invoice_number.group(1) if invoice_number else "Not found"
    order_date = date_match.group(0).strip() if date_match else "Not found"
    
    return invoice_number, order_date, customer, state, total_due

if uploaded_file:
    st.write(f"**Uploaded File:** {uploaded_file.name}")

    try:
        pdf_bytes = uploaded_file.read()
        images = convert_from_bytes(pdf_bytes)
        full_text = ""

        st.subheader("📄 Page Preview")
        st.image(images[0], caption="Page 1", use_column_width=True)
        processed_image = process_image(images[0])
        custom_config = r'--oem 3 --psm 6'
        page_text = pytesseract.image_to_string(processed_image, config=custom_config)
        full_text += page_text + "\n\n"

        if len(images) > 1:
            if st.checkbox("Show and OCR all pages"):
                for i, image in enumerate(images[1:], start=2):
                    st.image(image, caption=f"Page {i}", use_column_width=True)
                    processed_image = process_image(image)
                    page_text = pytesseract.image_to_string(processed_image, config=custom_config)
                    full_text += page_text + "\n\n"

        with st.expander("📝 Show OCR Text (All Pages)"):
            st.text(full_text)

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




