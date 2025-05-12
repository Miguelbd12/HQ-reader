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
import streamlit.components.v1 as components  # ✅ Needed for JS injection

st.set_page_config(page_title="Invoice Extractor", layout="centered")
st.title("📄 Invoice Extractor")
st.write("Upload multiple invoice PDFs and extract key information.")

# Custom CSS for buttons
st.markdown("""
    <style>
    .stButton>button {
        background-color: #28a745;
        color: white;
        border: none;
        padding: 10px 24px;
        text-align: center;
        font-size: 16px;
        border-radius: 4px;
    }
    .stButton>button:hover {
        background-color: #218838;
    }
    .stButton .clear-btn>button {
        background-color: transparent;
        color: #000;
        border: 1px solid #ddd;
        padding: 10px 24px;
    }
    .stButton .clear-btn>button:hover {
        background-color: transparent;
        border: 1px solid #ccc;
    }
    </style>
    """, unsafe_allow_html=True)

# Upload
uploaded_files = st.file_uploader("Choose invoice PDFs", type=["pdf"], accept_multiple_files=True)

# States of interest
US_STATES = ["IL", "MD", "MA", "NV", "NJ", "NY", "OH"]

# Run button
run_extraction = st.button("🚀 Run", type="primary")

# ✅ Clear button with full page reload
if st.button("🧹 Clear PDFs", key="clear_btn", help="Clear the uploaded PDFs"):
    components.html("""
        <script>
            window.location.reload();
        </script>
        """, height=0)

# Helper functions
def process_image(image):
    img_np = np.array(image)
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(blurred, 255,
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 11, 2)
    img_resized = cv2.resize(thresh, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    return Image.fromarray(img_resized)

def extract_state(text, customer):
    for st_code in US_STATES:
        if re.search(rf"\b{st_code}\b", customer.upper()):
            return st_code
    for st_code in US_STATES:
        if re.search(rf"\b{st_code}\b", text.upper()):
            return st_code
    return "Unknown"

def extract_invoice_data(text):
    invoice_number = re.search(r"(?:Invoice\s*(?:No\.?|#)?|Bill\s*#?)\s*[:\-]?\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    pst = pytz.timezone('US/Pacific')
    order_date = datetime.now(pytz.utc).astimezone(pst).strftime("%Y-%m-%d %H:%M:%S")

    total_due_match = re.search(r"(\d{1,3}(?:[.,]?\d{3})*(?:[.,]\d{2})?)\s*uss", text, re.IGNORECASE)
    total_due = "Not found"
    if total_due_match:
        try:
            total_amount = total_due_match.group(1).replace(".", "").replace(",", ".")
            total_due = "{:,.2f}".format(float(total_amount))
        except ValueError:
            total_due = "Invalid format"
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
        customer = re.sub(r"PAY TO THE ORDER OF N/A|GTINJ PAYMENT TERMS|PAYMENT TERMS|GTHL|GTI Nevada LLC\s*\.\s*N/A|GTIHL|GTIMA|GTIIL", "", customer, flags=re.IGNORECASE)

    state = extract_state(text, customer)
    invoice_number = invoice_number.group(1) if invoice_number else "Not found"

    return invoice_number, order_date, customer.strip(), state, total_due

# Extraction logic
if run_extraction and uploaded_files:
    all_data = []
    for uploaded_file in uploaded_files:
        try:
            pdf_bytes = uploaded_file.read()
            images = convert_from_bytes(pdf_bytes)
            full_text = ""

            for image in images:
                processed_image = process_image(image)
                text = pytesseract.image_to_string(processed_image, config='--oem 3 --psm 6')
                full_text += text + "\n\n"

            invoice_number, order_date, customer, state, total_due = extract_invoice_data(full_text)

            st.success(f"✅ Processed: {uploaded_file.name}")
            all_data.append({
                "Invoice Number": invoice_number,
                "Order Placed Date": order_date,
                "Customer": customer,
                "State": state,
                "Total Due": total_due
            })

        except Exception as e:
            st.error(f"❌ An error occurred with file {uploaded_file.name}: {e}")

    if all_data:
        df = pd.DataFrame(all_data)
        st.subheader("📊 Extracted Data")
        st.dataframe(df)

        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Invoices')

        st.download_button(
            label="📥 Download Excel File",
            data=buffer.getvalue(),
            file_name="invoice_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


