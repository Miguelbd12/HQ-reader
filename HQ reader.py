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
import pytz
from datetime import datetime

st.title("📄 Invoice Extractor")
st.write("Upload one or more invoice PDFs and extract key information.")

uploaded_files = st.file_uploader("Choose invoice PDFs", type=["pdf"], accept_multiple_files=True)

# List of US state abbreviations
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
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
    
    pst = pytz.timezone('US/Pacific')
    order_date = datetime.now(pytz.utc).astimezone(pst).strftime("%Y-%m-%d %H:%M:%S")

    total_due_match = re.search(r"(\d{1,3}(?:[.,]?\d{3})*(?:[.,]\d{2})?)\s*uss", text, re.IGNORECASE)
    total_due = "Not found"
    if total_due_match:
        total_amount = total_due_match.group(1)
        total_amount = total_amount.replace(".", "").replace(",", ".")
        total_due = "{:,.2f}".format(float(total_amount))
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

    customer_match = re.search(r"CUSTOMER[\n:]*\s*(.*?)(?:LICENSE|SHIP TO|BILL TO|INVOICE)", text, re.DOTALL | re.IGNORECASE)
    customer = "Not found"
    if customer_match:
        customer = re.sub(r'\n+', ' ', customer_match.group(1).strip())
        customer = re.sub(r"PAY TO THE ORDER OF N/A|GTINJ PAYMENT TERMS|PAYMENT TERMS|GTHL|GTI Nevada LLC\s*\.\s*N/A|GTIHL|GTIMA|GTIIL", "", customer, flags=re.IGNORECASE)

    st.write(f"**Raw Customer Data:** {customer}")

    state = extract_state(text, customer)
    invoice_number = invoice_number.group(1) if invoice_number else "Not found"

    return invoice_number, order_date, customer, state, total_due

if uploaded_files:
    all_data = []

    for uploaded_file in uploaded_files:
        st.write(f"**Processing File:** {uploaded_file.name}")
        try:
            pdf_bytes = uploaded_file.read()
            images = convert_from_bytes(pdf_bytes)
            full_text = ""

            st.subheader(f"📄 Page Preview - {uploaded_file.name}")
            st.image(images[0], caption=f"{uploaded_file.name} - Page 1", use_column_width=True)
            processed_image = process_image(images[0])
            custom_config = r'--oem 3 --psm 6'
            page_text = pytesseract.image_to_string(processed_image, config=custom_config)
            full_text += page_text + "\n\n"

            if len(images) > 1:
                if st.checkbox(f"Show and OCR all pages for {uploaded_file.name}"):
                    for i, image in enumerate(images[1:], start=2):
                        st.image(image, caption=f"{uploaded_file.name} - Page {i}", use_column_width=True)
                        processed_image = process_image(image)
                        page_text = pytesseract.image_to_string(processed_image, config=custom_config)
                        full_text += page_text + "\n\n"

            with st.expander(f"📝 Show OCR Text for {uploaded_file.name}"):
                st.text(full_text)

            invoice_number, order_date, customer, state, total_due = extract_invoice_data(full_text)

            st.subheader(f"🧾 Extracted Data for {uploaded_file.name}")
            st.write(f"**Invoice Number:** {invoice_number}")
            st.write(f"**Order Placed Date:** {order_date}")
            st.write(f"**Customer:** {customer}")
            st.write(f"**State:** {state}")
            st.write(f"**Total Due:** {total_due}")

            all_data.append({
                "File Name": uploaded_file.name,
                "Invoice Number": invoice_number,
                "Order Placed Date": order_date,
                "Customer": customer,
                "State": state,
                "Total Due": total_due
            })

        except Exception as e:
            st.error(f"An error occurred with file {uploaded_file.name}: {e}")

    if all_data:
        df = pd.DataFrame(all_data)
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Invoice Data')

        st.download_button(
            label="📥 Download All Invoice Data as Excel",
            data=buffer.getvalue(),
            file_name="all_invoices.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
