import os
import re
import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class LLMHandler:
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.openrouter_headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/yourusername/email-bot",
        }
        #self.model_id = 'mistralai/mistral-7b-instruct'  # $0.03/M in, $0.055/M out
        self.model_id = "mistralai/mistral-small-24b-instruct-2501:free"  # Free model
        self.llm_timeout = 5  # response timeout in seconds

    def validate_email(self, email_sender, email_subject, email_body, model_id=None, subject_cutoff=50, body_cutoff=500):
        """Identify spam/DoS using a free or cheap OpenRouter LLM.

        Returns True if email appears valid.
        """
        model_id = model_id or self.model_id
        if len(email_subject) > subject_cutoff:
            email_subject = email_subject[:subject_cutoff] + f"... (skipping {len(email_subject) - subject_cutoff} chars)"

        if len(email_body) > body_cutoff:
            words_skipped = count_words(email_body) - count_words(email_body[:body_cutoff])
            email_body = email_body[:body_cutoff] + f"...\n(skipping {words_skipped} words)"

        system_prompt = (
            'You are a security-focused email classifier. Your goal is to determine whether an email '
            'is a legitimate request to a human person or spam/malicious content. '
            'Instructions:\n'
            'Classify the senders intent as either "normal" (legitimate) or "malicious" (spam, phishing, scam, DoS, or abuse).\n\n'
            'Consider these factors:\n'
            '- High word count with little meaningful content: "malicious"\n'
            '- Urgent financial requests or threats: "malicious"\n'
            '- Excessive links or attachments from unknown senders: "malicious"\n'
            '- Repeated or bot-like phrasing: "malicious"\n'
            '- Empty or random content: "malicious"\n'
            '- Polite, well-structured requests with intelligible content: "normal"\n\n'
            'Never output explanations, respond with a single token: If you classify the email as "normal" respond with "True", otherwise "False".'
        )

        user_prompt = f"""Email from {email_sender}:
        Subject: {email_subject}
        Content: \n\n{email_body}\n"""

        try:
            response = requests.post(
                self.openrouter_base_url,
                headers=self.openrouter_headers,
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=self.llm_timeout
            )

            if response.status_code == 200:
                response = response.json()["choices"][0]["message"]["content"].strip()
                reasoning = ''

                # Normal LLM response
                if response.lower() in {"true", "false"}:
                    return 'pass' if response.lower() == 'true' else 'block', reasoning

                # Handle output from various models
                if '</think>' in response:
                    print("DEBUG response with thinking:", response)
                    reasoning, _, response = response.partition('</think>')

                boxed_match = re.search(r"\\boxed\{(.*?)\}", response)
                if boxed_match:
                    response = boxed_match.group(1)
                    if response.lower() in {"true", "false"}:
                        return 'pass' if response.lower() == 'true' else 'block', reasoning
                    else:
                        return 'error', reasoning + f'\nResponse: {response}'

                # Unexpected LLM response
                print(f'DEBUG: unexpected response: "{response}"')
                return 'error', response

            else:
                return 'error', f"Error generating response: {response.status_code} - {response.text}"

        except Exception as e:
            return 'error', f"Error generating response: {str(e)}"

    # TODO: moderation should take subject into account as well
    def moderate_email(self, email_content):
        """Check if email content is appropriate using OpenAI's moderation API."""
        try:
            response = self.openai_client.moderations.create(input=email_content)
            result = response.results[0]

            # If any category is flagged, consider it inappropriate
            is_appropriate = not result.flagged

            if not is_appropriate:
                # Get the categories that were flagged
                flagged_categories = []
                categories = result.categories

                # Check each category
                if categories.hate:
                    flagged_categories.append("hate")
                if categories.hate_threatening:
                    flagged_categories.append("hate/threatening")
                if categories.self_harm:
                    flagged_categories.append("self-harm")
                if categories.self_harm_intent:
                    flagged_categories.append("self-harm/intent")
                if categories.self_harm_instructions:
                    flagged_categories.append("self-harm/instructions")
                if categories.sexual:
                    flagged_categories.append("sexual")
                if categories.sexual_minors:
                    flagged_categories.append("sexual/minors")
                if categories.violence:
                    flagged_categories.append("violence")
                if categories.violence_graphic:
                    flagged_categories.append("violence/graphic")
                if categories.harassment:
                    flagged_categories.append("harassment")
                if categories.harassment_threatening:
                    flagged_categories.append("harassment/threatening")
                if categories.illicit:
                    flagged_categories.append("illicit")
                if categories.illicit_violent:
                    flagged_categories.append("illicit/violent")

                reason = f"INAPPROPRIATE: Content was flagged for: {', '.join(flagged_categories)}"
            else:
                reason = "APPROPRIATE"

            return is_appropriate, reason

        except Exception as e:
            return False, f"Error during moderation: {str(e)}"

    def generate_response(self, email_content, subject, sender_name):
        """Generate an intelligent response using OpenRouter's free LLM."""
        system_prompt = """You are an accountability partner bot that helps users achieve their goals through email communication.
        Your responses should be:
        1. Encouraging and supportive
        2. Focused on the user's goals and progress
        3. Professional but friendly
        4. Brief and concise
        5. Action-oriented when appropriate
        
        If the email is a "start" message, welcome the user and acknowledge their goal.
        If it's an update, provide encouragement and ask about next steps or challenges.
        """

        user_prompt = f"""Email from {sender_name}:
        Subject: {subject}
        Content: {email_content}
        
        Please provide a supportive response that helps them stay accountable to their goals."""

        try:
            response = requests.post(
                self.openrouter_base_url,
                headers=self.openrouter_headers,
                json={
                    "model": "mistralai/mistral-7b-instruct",  # Free model
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,  # Balanced between creativity and consistency
                },
                timeout=self.llm_timeout
            )

            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
            else:
                return f"Error generating response: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Error generating response: {str(e)}"

def count_words(text):
    """Count words safely."""
    words = re.findall(r'\b\w+\b', text)  # Extract words safely
    return len(words)
