# claim_time_normalizer.py

from datetime import datetime, timedelta
import re
import os
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY_1")

class ClaimTimeNormalizer:
    def __init__(self, api_key: str = GROQ_API_KEY, model_name: str = "llama3-8b-8192"):
        self.api_key = api_key
        self.model_name = model_name
        self.client = Groq(api_key=api_key)

    def _strip_boilerplate_prefixes(self, text: str) -> str:
        """
        Removes common prefixes added by LLMs like 'The claim states that' or similar.
        """
        # List of common prefixes to remove if they appear at the beginning
        boilerplate_patterns = [
            r'^["“]?(the\s+claim\s+states\s+that[:,]?)["”]?\s*',
            r'^["“]?(according\s+to\s+the\s+claim[:,]?)["”]?\s*',
            r'^["“]?(it\s+is\s+claimed\s+that[:,]?)["”]?\s*',
        ]

        for pattern in boilerplate_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text.strip()


    def normalize(self, claim: str, today=None) -> str:
        today = today or datetime.today()
        intermediate_claim = self._apply_regex_replacements(claim, today)

        if intermediate_claim == claim:
            # If nothing changed, use LLM as fallback
            raw_output = self._normalize_with_groq(claim, today)
            cleaned = self._strip_boilerplate_prefixes(raw_output)
            return cleaned
        else:
            return intermediate_claim


    def _get_last_week_range(self, today: datetime) -> str:
        start_of_this_week = today - timedelta(days=today.weekday())
        start_of_last_week = start_of_this_week - timedelta(weeks=1)
        end_of_last_week = start_of_this_week - timedelta(days=1)
        return f"between {start_of_last_week.strftime('%B %-d')} and {end_of_last_week.strftime('%B %-d, %Y')}"

    def _get_last_month_range(self, today: datetime) -> str:
        year = today.year
        month = today.month - 1
        if month == 0:
            month = 12
            year -= 1
        month_name = datetime(year, month, 1).strftime("%B")
        return f"in {month_name} {year}"

    def _get_last_year_range(self, today: datetime) -> str:
        last_year = today.year - 1
        return f"in {last_year}"


    def _apply_regex_replacements(self, text: str, today: datetime) -> str:
        # Handle fixed replacements first
        fixed = [
            (r"\btoday\b", today),
            (r"\byesterday\b", today - timedelta(days=1)),
            (r"\btomorrow\b", today + timedelta(days=1)),
            (r"\bthe day before yesterday\b", today - timedelta(days=2)),
            (r"\b(\d+)\s+days ago\b", lambda m: today - timedelta(days=int(m.group(1)))),
            (r"\b(\d+)\s+weeks ago\b", lambda m: today - timedelta(weeks=int(m.group(1)))),
            (r"\b(\d+)\s+months ago\b", lambda m: self._subtract_months(today, int(m.group(1)))),
        ]

        for pattern, replacement in fixed:
            if isinstance(replacement, datetime):
                date_str = replacement.strftime("%B %-d, %Y")
                text = re.sub(pattern, date_str, text, flags=re.IGNORECASE)
            else:
                text = re.sub(pattern, lambda m: replacement(m).strftime("%B %-d, %Y"), text, flags=re.IGNORECASE)

        # Handle vague ranges: last week, last month, last year
        vague_replacements = {
            r"\blast week\b": self._get_last_week_range(today),
            r"\blast month\b": self._get_last_month_range(today),
            r"\blast year\b": self._get_last_year_range(today),
        }

        for pattern, replacement_text in vague_replacements.items():
            text = re.sub(pattern, replacement_text, text, flags=re.IGNORECASE)

        return text

    def _subtract_months(self, dt: datetime, months: int) -> datetime:
        """Subtract `months` months from a datetime object."""
        month = dt.month - months
        year = dt.year + month // 12
        month = month % 12
        if month == 0:
            month = 12
            year -= 1
        day = min(dt.day, 28)  # to avoid month-end issues
        return datetime(year, month, day)

    def _normalize_with_groq(self, claim: str, today: datetime) -> str:
        try:
            today_str = today.strftime("%B %-d, %Y")
            prompt = (
                f"The current date is {today_str}.Use it to calculate relative time ranges.\n"
                f"The following is a user-entered claim:\n\"{claim}\"\n"
                f"Replace only the vague or relative time expressions (e.g., last year, last month, recently, two weeks ago) with an explicit date range like: between [start_date] and [end_date].\n"
                f"Do not change the structure or wording of the claim.\n"
                f"Return only the updated claim. Do not add any explanations.\n"
                f"Updated claim:"
            )

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
            )

            return response.choices[0].message.content.strip()
        except Exception as e:
            print("⚠️ Groq fallback failed:", e)
            return claim
