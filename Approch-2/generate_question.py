import os
import re
import spacy
from groq import Groq

# Load spaCy English model
nlp = spacy.load("en_core_web_sm")
from dotenv import load_dotenv
import os

load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY_6")

# Initialize Groq client
client = Groq(api_key=groq_api_key)

def is_simple_claim(claim):
    """
    Use NLP to check if the claim is short and has named entities.
    If so, it's likely safe to use a template instead of LLM.
    """
    doc = nlp(claim)
    num_ents = len(doc.ents)
    num_tokens = len(doc)
    # Rule: short claim + has at least one entity → simple
    return num_tokens <= 12 and num_ents >= 1

def template_question(claim):
    """
    Rule-based template: prepend 'Is it true that ...'
    """
    return f"Is it true that {claim.strip().rstrip('.')}?"

def generate_two_questions_llm(claim):
    """
    Use Groq LLM to produce two different yes/no questions from the claim.
    Few-shot style prompt.
    """
    prompt = f"""
Generate two different yes/no questions that verify the given claim.

Claim: Humans need oxygen to survive.
Questions:
1) Do humans need oxygen to survive?
2) Is it true that humans need oxygen to survive?

Claim: {claim}
Questions:
1)
2)
""".strip()

    completion = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=100
    )
    return completion.choices[0].message.content.strip()

def fix_question(question):
    """
    NLP/regex post-process:
    - Capitalize first letter
    - Add '?' if missing
    - Enforce yes/no pattern if needed
    """
    question = question.strip()
    if not question.endswith("?"):
        question += "?"
    question = question[0].upper() + question[1:]
    # Enforce that it starts with a yes/no verb (basic check)
    if not re.match(r"^(Is|Are|Was|Were|Do|Does|Did|Can|Could|Should|Would|Has|Have|Will|May|Might|Is it true)", question, re.IGNORECASE):
        question = "Is it true that " + question
    return question

def generate_questions(claim):
    """
    Full pipeline: NLP pre-check → template or LLM → NLP post-process.
    Always returns 2 versions for consistency.
    """
    claim = claim.strip()

    if is_simple_claim(claim):
        # Simple claim → use rule-based + 1 LLM variant
        print("✅ Using NLP template + 1 LLM version (hybrid).")
        q1 = template_question(claim)
        llm_questions = generate_two_questions_llm(claim)
        # Extract only the second LLM version (from the LLM output)
        match = re.search(r"2\)\s*(.*)", llm_questions)
        q2 = match.group(1).strip() if match else "Could not parse LLM second question."
    else:
        # Complex claim → generate both with LLM
        print("✅ Using LLM for both versions.")
        llm_questions = generate_two_questions_llm(claim)
        match1 = re.search(r"1\)\s*(.*)", llm_questions)
        match2 = re.search(r"2\)\s*(.*)", llm_questions)
        q1 = match1.group(1).strip() if match1 else "Could not parse LLM first question."
        q2 = match2.group(1).strip() if match2 else "Could not parse LLM second question."

    # Post-process both
    q1 = fix_question(q1)
    q2 = fix_question(q2)

    return [q1, q2]


# -------- Run it --------
if __name__ == "__main__":
    user_claim = input("Enter a claim: ").strip()
    questions = generate_questions(user_claim)

    print("\n🏆 Final Neutral Yes/No Questions:")
    for i, q in enumerate(questions, 1):
        print(f"{i}. {q}")
