def extract_invoice_data(text):
    invoice_number = re.search(r"(?:Invoice\s*(?:No\.?|#)?|Bill\s*#?)\s*[:\-]?\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    
    # Using the current date and time for "Order Placed Date" in PST
    pst = pytz.timezone('US/Pacific')
    order_date = datetime.now(pytz.utc).astimezone(pst).strftime("%Y-%m-%d %H:%M:%S")  # Convert to PST and format as string
    
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
        
        # Remove "GTIMA" and "GTIIL" from the customer string
        customer = re.sub(r"GTIMA", "", customer, flags=re.IGNORECASE)  # Removing "GTIMA" (case-insensitive)
        customer = re.sub(r"GTIIL", "", customer, flags=re.IGNORECASE)  # Removing "GTIIL" (case-insensitive)
        
        # Remove "GTI Nevada LLC . NIA"
        customer = re.sub(r"GTI Nevada LLC\s*\.\s*NIA", "", customer, flags=re.IGNORECASE)  # Removing the specified text

    st.write(f"**Raw Customer Data:** {customer}")

    state = extract_state(text, customer)
    invoice_number = invoice_number.group(1) if invoice_number else "Not found"
    
    return invoice_number, order_date, customer, state, total_due


