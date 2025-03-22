import os
import requests
from dotenv import load_dotenv

load_dotenv()


class LLMHandler:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/yourusername/email-bot",  # Replace with your repo URL
        }

    def moderate_email(self, email_content):
        """Check if email content is appropriate."""
        prompt = f"""You are an email moderation system. Analyze this email content and determine if it's appropriate for an accountability partner bot.
        Consider:
        - Is it respectful and professional?
        - Does it contain harmful or inappropriate content?
        - Is it related to personal goals and accountability?
        
        Email content:
        {email_content}
        
        Respond with only "APPROPRIATE" or "INAPPROPRIATE" followed by a brief reason.
        """

        try:
            response = requests.post(
                self.base_url,
                headers=self.headers,
                json={
                    "model": "mistralai/mistral-7b-instruct",  # Free model
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,  # Low temperature for consistent moderation
                },
            )

            if response.status_code == 200:
                result = response.json()["choices"][0]["message"]["content"].strip()
                is_appropriate = result.startswith("APPROPRIATE")
                return is_appropriate, result
            else:
                return False, f"Error: {response.status_code} - {response.text}"

        except Exception as e:
            return False, f"Error during moderation: {str(e)}"
