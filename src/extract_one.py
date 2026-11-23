import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel


class OrderLine(BaseModel):
    product: str
    quantity: Optional[int]
    unit_price: Optional[float]
    currency: Optional[str]


class Order(BaseModel):
    is_order: bool
    sender_name: Optional[str]
    sender_company: Optional[str]
    sender_email: Optional[str]
    order_reference: Optional[str]
    order_date: Optional[str]
    lines: list[OrderLine]
    notes: Optional[str]


SYSTEM_PROMPT = """You extract purchase orders from business emails for a perfume and cosmetics trading company.
Rules:
- Only use information written in the email. Never guess or invent values.
- If a value is missing or unclear (e.g. "same price as last month"), set it to null and explain in notes.
- Convert quantities written in words to numbers (e.g. "two dozen" = 24).
- unit_price is the price per single unit, as a number without the currency symbol.
- currency is a 3-letter code (e.g. AED, USD) or null if not stated.
- If the email is not an order (e.g. a complaint or question), set is_order to false and lines to an empty list.
"""

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3.6-flash"


def extract_order(email_text: str) -> Order:
    response = client.models.generate_content(
        model=MODEL,
        contents=email_text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=Order,
            temperature=0,
        ),
    )
    return response.parsed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/extract_one.py emails/email_01.txt")
        sys.exit(1)

    email_path = Path(sys.argv[1])
    email_text = email_path.read_text(encoding="utf-8")

    order = extract_order(email_text)
    print(order.model_dump_json(indent=2))