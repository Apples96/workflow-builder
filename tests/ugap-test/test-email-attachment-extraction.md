# Test: Email + Attachment Cross-Document Extraction

Test for extracting and combining information from an email and its referenced attachment (investment presentation). Exercises multi-doc upload, cross-document data aggregation, and structured report generation with many fields.

## Input documents (upload in this order)
- Document 1: `emad-bakeries/02_FW_Emad_Bakeries_Email.docx` — Forwarded email referencing an investment opportunity
- Document 2: `emad-bakeries/01_Emad_Bakeries_Presentation.pdf` — Investment presentation (the attachment)

## Workflow description (paste into the workflow builder)

```
The user uploads 2 documents in the following order:
- document 1 type "Email" (a forwarded email about an investment opportunity)
- document 2 type "Attachment" (the investment presentation referenced in the email)

Retrieve the document IDs and create a mapping Document type : Document ID for use in subsequent steps.

STEP 1: Extract email metadata
- Use doc search on the Email document to extract: sender name, recipient name, date sent, subject line, and any brief summary or forwarding note.
- Store each field as a separate string variable: sender_name, recipient_name, email_date, email_subject, email_note.

STEP 2: Extract investment details from attachment
- Use doc search on the Attachment document to extract the following investment opportunity details:
  - Company name
  - Sector / industry
  - Country / location
  - Investment amount or range
  - Revenue or EBITDA figures (any financial metrics available)
  - Key growth drivers or investment highlights (as a short summary paragraph)
- Store each field as a separate string variable: company_name, sector, location, investment_amount, financial_metrics, investment_highlights.

STEP 3: Compile investment summary report
- Retrieve all variables from steps 1 and 2.
- Using pure Python (NO API calls, NO LLM), compile a structured summary report as a single string with the following sections:
  - EMAIL METADATA: sender, recipient, date, subject
  - INVESTMENT OVERVIEW: company name, sector, location, investment amount
  - FINANCIAL DETAILS: revenue/EBITDA metrics
  - KEY HIGHLIGHTS: growth drivers and investment thesis
- Use named string formatting (e.g. "{company_name}") rather than positional indices to avoid formatting errors.
- Store the compiled report as final_report (string).
```

## Expected behavior
- Cell 1 (mapping): Creates document_mapping with IDs for both documents
- Cell 2 (email extraction): doc_search on email document, extracts 5 metadata fields
- Cell 3 (attachment extraction): doc_search on presentation, extracts 6 investment fields
- Cell 4 (report compilation): Pure Python string formatting with named placeholders, outputs structured report
- Exercises: multi-doc upload, email+attachment pattern, cross-document aggregation, named format strings, structured report

## Approximate timing
- Planning: ~25s
- Code generation (4 cells): ~2-3 min
- Execution (4 cells): ~3-4 min (2 Paradigm searches + 1 mapping + 1 Python native)
- Total: ~5-7 min
