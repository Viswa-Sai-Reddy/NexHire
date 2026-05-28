# import pickle, base64
# from googleapiclient.discovery import build
# from google.auth.transport.requests import Request
# from email.mime.text import MIMEText

# # Load and refresh token
# with open('.secret/gmail_token.pkl', 'rb') as f:
#     creds = pickle.load(f)

# if creds.expired and creds.refresh_token:
#     creds.refresh(Request())

# service = build('gmail', 'v1', credentials=creds)

# msg = MIMEText("Test from NexHire!")
# msg['Subject'] = "Test"
# msg['From'] = "viswasaireddy96033@gmail.com"
# msg['To'] = "viswasaireddy96033@gmail.com"

# raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
# result = service.users().messages().send(
#     userId='me', body={'raw': raw}
# ).execute()

# print(f"✅ Email sent! Message ID: {result['id']}")


import asyncio
import sys
sys.path.insert(0, '.')

from datetime import date
from app.modules.ai.certificate import _render_pdf
from app.infrastructure import azure_blob

async def main():
# Use the same intern_id from your blob filename
    intern_id = "9d063143-a778-4140-b34f-1524abc99603"

    pdf_bytes = _render_pdf(
    intern_name="VISWA SAI REDDY N",
    citation="This is to certify that VISWA SAI REDDY N has successfully completed an internship titled 'the' focused on LV thesuhjsdhbcb. The intern demonstrated a positive attitude and completed the project to the satisfaction of the mentor.",
    mentor_name="Demo Mentor Lead",
    issue_date=date.today(),
    project_title="the"
    )

    print(f"PDF size: {len(pdf_bytes)} bytes")
    print(f"Header: {pdf_bytes[:4]}")

    if pdf_bytes[:4] != b'%PDF':
        print("❌ Still not a valid PDF!")
        return

    blob_key = f"certificates/{intern_id}.pdf"
    await azure_blob.upload(
        container="documents",
        data=pdf_bytes,
        content_type="application/pdf",
        filename=f"certificate-{intern_id}.pdf",
        blob_key=blob_key,
        overwrite=True,
    )
    print("✅ Certificate regenerated and uploaded!")

asyncio.run(main())