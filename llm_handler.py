import os
import re
import json
import textwrap
import requests
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import email
import numpy as np
from utils import count_words, format_emails
import tiktoken

load_dotenv()


def get_available_models():
    """Returns a dict of all models and their specs, as provided via API."""
    try:
        response = requests.get("https://openrouter.ai/api/v1/models")
        data = response.json()['data']
    except Exception as e:
        print(f"Error in get_available_models: {e}")
        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            pass
    return {model_data['id']: model_data for model_data in data}


# Try to get list of available OpenRouter models on module import
available_models = get_available_models()


models_supporting_structured_output = {
    'google/gemini-2.5-pro-exp-03-25:free',
    'google/gemini-2.0-flash-lite-preview-02-05:free',
    'google/gemma-3-27b-it:free',
    'google/gemini-2.0-flash-exp:free',
    'meta-llama/llama-3.1-8b-instruct',  # $/M tokens in/out: 0.1/0.1
    'mistralai/mistral-small-24b-instruct-2501', # $/M tokens in/out: 0.1/0.3
    'mistralai/mistral-small-3.1-24b-instruct',  # $/M tokens in/out: 0.1/0.3
    'openai/gpt-4o-mini',  # $/M tokens in/out: 0.15/0.6
}


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


    def get_rate_limits(self):
        try:
            response = requests.get(self.openrouter_base_url, headers=self.openrouter_headers)
            data = response.json()['data']
            limit = data['limit']
            print(f'label: {data["label"]}, {data["usage"]}/{data["limit"] or "inf"} credits used {"(free tier)" if data["is_free_tier"] else ""}')
            print(f'Rate limit: {limit["requests"]} per {limit["interval"]}')
        except Exception as e:
            print(f"Error in get_rate_limits: {e}")
            try:
                print(json.dumps(response.json(), indent=2))
            except Exception:
                pass


    def get_model_pricing(self, model_id=None):
        """Returns tokenizer, input pricing, output pricing (USD/token)."""
        model_id = model_id or self.model_id
        try:
            data = available_models[model_id]
            tokenizer = data['architecture']['tokenizer']
            pricing_in = float(data['pricing']['prompt'])
            pricing_out = float(data['pricing']['completion'])
        except KeyError as e:
            print(f"Error: missing pricing data {e} for model {model_id}")
            return None, None, None
        return tokenizer, pricing_in, pricing_out


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
            'is a legitimate request to a human person or spam/malicious content.\n'
            'Instructions:\n'
            'Classify the senders intent as either normal (legitimate) or malicious (spam, phishing, scam, DoS, or abuse). '
            'Normal emails shall be labelled "pass", malicious emails shall be labelled "block".\n\n'
            'Consider these factors:\n'
            '- High word count with little meaningful content: "block"\n'
            '- Urgent financial requests or threats: "block"\n'
            '- Excessive links or attachments from unknown senders: "block"\n'
            '- Repeated or bot-like phrasing: "block"\n'
            '- Empty or random content: "block"\n'
            '- Polite, well-structured requests with intelligible content: "pass"\n\n'
            'Never output explanations, respond with "pass" or "block"\n'
        )

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "validation_result",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "classification": {
                            "type": "string",
                            "enum": ["pass", "block"],
                            "description": "Classification of the email legitimacy as either 'pass' or 'block'."
                        }
                    },
                    "required": ["classification"],
                    "additionalProperties": False
                }
            }
        }

        user_prompt = f"""Email from {email_sender}:
        Subject: {email_subject}
        Content: \n\n{email_body}\n"""

        openrouter_json = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if model_id in models_supporting_structured_output:
            openrouter_json['response_format'] = response_format
            expecting_structured_output = True
        else:
            expecting_structured_output = False

        try:
            response = requests.post(
                self.openrouter_base_url,
                headers=self.openrouter_headers,
                json=openrouter_json,
                timeout=self.llm_timeout
            )

            if response.status_code == 200:
                if "choices" not in response.json():
                    # Handle errors from LLM provider
                    if 'error' in response.json():
                        response = response.json()['error']
                        print(response['message'])
                        if 'metadata' in response and 'raw' in response['metadata']:
                            print(response['metadata']['raw'])
                            return 'error', response['message']
                        elif response['message'] == 'Rate limit exceeded: free-models-per-min':
                            return 'error', 'wait a minute'
                        elif response['message'] == 'Rate limit exceeded: free-models-per-day':
                            return 'error', 'wait a day'
                        else:
                            return 'error', response['message']
                    else:
                        print("Unexpected response despite status_code 200.")
                        for key, value in response.json().items():
                            print(f'{key}: {value}')
                    return 'error', ''

                response = response.json()["choices"][0]["message"]["content"].strip()
                reasoning = ''

                # Structured LLM response
                if expecting_structured_output:
                    try:
                        data = json.loads(response)  # Safely parse JSON
                        if isinstance(data, dict) and "classification" in data:
                            classification = data["classification"]
                            assert isinstance(classification, str), f'classification has unexpected type {type(classification)}'
                            return classification, ''
                        else:
                            print("Invalid response format:", data)
                            return "error", "LLM sent structured output with invalid format"
                    except json.JSONDecodeError:
                        print("Failed to parse JSON from structured output:", response)
                        return "error", "LLM sent corrupt structured output"

                # Normal LLM response
                response = response.strip('"\'.`').lower()
                if response.lower() in {"pass", "block"}:
                    return 'pass' if response.lower() == 'pass' else 'block', reasoning

                # Handle output from various models
                if '</think>' in response:
                    print("DEBUG response with thinking:", response)
                    reasoning, _, response = response.partition('</think>')

                boxed_match = re.search(r"\\boxed\{(.*?)\}", response)
                if boxed_match:
                    response = boxed_match.group(1)
                    if response.lower() in {"pass", "block"}:
                        return 'pass' if response.lower() == 'pass' else 'block', reasoning
                    else:
                        return 'error', reasoning + f'\nResponse: {response}'

                # Unexpected LLM response
                print(f'DEBUG: unexpected response: "{response}"')
                return 'error', response

            else:
                return 'error', f"Error generating response: {response.status_code} - {response.text}"

        except Exception as e:
            return 'error', f"Error generating response: {str(e)} ({type(e)})"  # 'raw'


    def schedule_response(self, emails, model_id=None, bot_address='acp@startup.com', now=None,
                          verbose=False, DEBUG=False):
        """Decide whether a reponse is due.

        This agent gets the "From", "Date" and "body" attributes of each
        email in `emails` and the current date/time.

        It returns two values in json format:
        - response_is_due (bool): whether it would be appropriate to repond to the last
                                  user email right now.
        - probability (float):    likelihood that the user expects a response or reminder
                                  from the assistant right now.
        """
        model_id = model_id or self.model_id

        system_prompt = """
            You are an AI assistant that helps determine when to respond to email conversations.

            Analyze the email history and determine if a response is due based on:
            1. Time elapsed since the last email
            2. Whether the last email was from the user or the assistant
            3. Whether the last email contains a user question or request that needs a response
            4. Whether user and assistant have agreed on a schedule when to check in again
            5. If the user wanted to report back by now, a reponse is due

            Return your decision in JSON format with these fields:
            - response_is_due (boolean): true if a response should be sent now, false otherwise
            - probability (float): between 0.0 and 1.0, representing the likelihood that a response is expected

            Only return valid JSON with these two fields and no additional text.
            """
        system_prompt = textwrap.dedent(system_prompt)

        # Deterministic checks
        if len(emails) == 0:
            print("EMPTY list of emails!")
            return
        if emails[-1].get("From", "Unknown") == bot_address:
            # Don't respond to self
            return dict(response_is_due=False, probability=0.0)
        if (len(emails) == 1) and (emails[0].get("From", "Unknown") != bot_address):
            # Always respond to first user mail
            return dict(response_is_due=True, probability=1.0)

        # Create the user prompt with the email history
        email_history = format_emails(emails, style='json', bot_address=bot_address)
        now = now or datetime.now()
        user_prompt = (
            "Here is the email conversation history:\n"
            f"{email_history}\n"
            f"\nCurrent time: {email.utils.format_datetime(now)[:-9]}\n\n"
            "Based on this information, determine if a response is due now."
            )

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "scheduling_decision",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "response_is_due": {
                            "type": "boolean",
                            "description": ("Whether it's appropriate to respond to the last "
                                            "user email right now")
                        },
                        "probability": {
                            "type": "number",
                            "description": ("Likelihood between 0 and 1 that the user expects "
                                            "a response or reminder from the assistant by now")
                        }
                    },
                    "required": ["response_is_due", "probability"],
                    "additionalProperties": False
                }
            }
        }

        openrouter_json = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,  # Lower temperature for more deterministic responses
        }

        if model_id in models_supporting_structured_output:
            openrouter_json['response_format'] = response_format
        else:
            print(f"WARNING: schedule_response uses model w/o response_format: {model_id}")

        if verbose:
            print(f"System Prompt:\n{system_prompt}")
            print(f"User Prompt:\n{user_prompt}")

        if DEBUG:
            return {'response_is_due': False, 'probability': 0.5}  # Skip LLM call

        try:
            response = requests.post(
                self.openrouter_base_url,
                headers=self.openrouter_headers,
                json=openrouter_json,
                timeout=self.llm_timeout
            )

            if response.status_code == 200:
                if "choices" not in response.json():
                    # Handle errors from LLM provider
                    if 'error' in response.json():
                        error = response.json()['error']
                        print(error['message'])
                        if 'metadata' in error and 'raw' in error['metadata']:
                            print(error['metadata']['raw'])
                    else:
                        print(response.json())
                    return {
                        "response_is_due": False,
                        "probability": 0.0,
                        "error": f"Error: {response.status_code} - {response.text}"
                    }
                content = response.json()["choices"][0]["message"]["content"].strip()

                # Parse the JSON response
                try:
                    result = json.loads(content)
                    # Validate the response has the required fields
                    if "response_is_due" in result and "probability" in result:
                        result["probability"] = np.clip(result["probability"], .05, .95).item()
                        return result
                    else:
                        return {
                            "response_is_due": False,
                            "probability": 0.0,
                            "error": "Invalid response format from LLM"
                        }
                except json.JSONDecodeError:
                    # If the response isn't valid JSON, try to extract it using regex
                    response_pattern = r'"response_is_due"\s*:\s*(true|false)'
                    probability_pattern = r'"probability"\s*:\s*([0-9]*\.?[0-9]+)'

                    response_match = re.search(response_pattern, content, re.IGNORECASE)
                    probability_match = re.search(probability_pattern, content)

                    if response_match and probability_match:
                        return {
                            "response_is_due": response_match.group(1).lower() == "true",
                            "probability": float(probability_match.group(1)),
                        }
                    else:
                        return {
                            "response_is_due": False,
                            "probability": 0.0,
                            "error": "Failed to parse LLM response"
                        }
            else:
                return {
                    "response_is_due": False,
                    "probability": 0.0,
                    "error": f"Error: {response.status_code} - {response.text}"
                }

        except Exception as e:
            return {
                "response_is_due": False,
                "probability": 0.0,
                "error": f"Error: {str(e)}"
            }

    def schedule_response_v2(self, emails, model_id=None, bot_address='acp@startup.com', now=None,
                             verbose=False, DEBUG=False):
        """Decide whether a reponse is due.

        This agent gets the "From", "Date" and "body" attributes of each
        email in `emails` and the current date/time.

        It returns two values in json format:
        - response_is_due (bool): whether it would be appropriate to repond to the last
                                  user email right now.
        - probability (float):    likelihood that the user expects a response or reminder
                                  from the assistant right now.

        The system prompt has auxiliary tasks that might be easier for the LLM, the return values are
        then inferred deterministically.
        """
        model_id = model_id or self.model_id

        system_prompt = """
            You support an AI assistant that plays the role of an accountability partner for a human user.
            Your task is to help the assistant with sending responses to the user timely and schedule
            reminder messages when the user has committed to check-in with the assistant but is overdue.

            Analyze the conversation regarding scheduling and commitments and predict:
            1. Who might send the next message, user or assistant?
            2. When might the next message be sent? Predict the next message's date and time!

            Also analyze the last user message carefully: If the user expresses any doubt,
            asks a question, or simply needs more advice or encouragement,
            the assistant might respond again to address those concerns.

            Only if the user gives the impression that he/she wants to end the conversation for now,
            assume a scheduled response by the assistant or user when they intend to check in again.

            Return your predictions in JSON format with these fields:
            - analysis (str): summarize questions (implicit or explicit) from the last message and explain who will respond next and with what intent
            - assistant_is_next (boolean): true if the assistant might send the next message, false otherwise
            - date (str): date and time of next expected message in email (RFC 2822) format

            Only return valid JSON with these three fields and no additional text. Here are some examples, complete the last one:

            <Input>
            From: user
            Date: Mon, 31 Mar 2025 14:35
            Content: OK, I'm really pumped now, I will see how the first week will go, will report you next Friday.
            ---
            From: assistant
            Date: Mon, 31 Mar 2025 14:40
            Content: Looking forward to the update!

            <JSON>
            {"analysis": "The user has no questions and will respond next to report how the first week went.", "assistant_is_next": false, "date": "Fri, 04 Apr 2025 14:35"}

            <Input>
            From: user
            Date: Sun, 30 Mar 2025 16:30
            Content: I have to go now, Sunday evening works great for me. Talk to you in a two weeks!

            <JSON>
            {"analysis": "The user has no questions and will respond next to continue the conversation.", "assistant_is_next": false, "date": "Sun, 13 Apr 2025 19:00"}

            <Input>
            From: user
            Date: Wed, 02 Apr 2025 11:30
            Content: Sounds perfect, I'll let you know on Wednesday how the session went! Any final advice?

            <JSON>
            {"analysis": "The user agrees to report back on Wednesday but asks for final advice. The assistant might respond next to give that advice.", "assistant_is_next": true, "date": "Wed, 02 Apr 2025 11:33"}

            <Input>
            From: user
            Date: Sat, 05 Apr 2024 16:00
            Content: Twice a week sounds a lot. Let's see what I can do.

            <JSON>
            {"analysis": "The user has doubts. The assistant will respond next to address these doubts.", "assistant_is_next": true, "date": "Sat, 05 Apr 2024 16:03"}

            <Input>
            From: user
            Date: Tue, 08 Jul 2024 22:00
            Content: Great! Should I takes notes when this happens? Could be an idea. I'm looking forward to our next session!

            <JSON>
            {"analysis": "The user asks about taking notes. The assistant might respond to that idea", "assistant_is_next": true, "date": "Tue, 08 Jul 2024 22:03"}
            """
        system_prompt = textwrap.dedent(system_prompt)

        # Deterministic checks
        if len(emails) == 0:
            print("ERROR: empty list of emails")
            return dict(error='ERROR: empty list of emails')
        if emails[-1].get("From", "Unknown") == bot_address:
            # Don't respond to self
            return dict(reasoning='deterministic', response_is_due=False, probability=0.0)
        if (len(emails) == 1) and (emails[0].get("From", "Unknown") != bot_address):
            # Always respond to first user mail
            return dict(reasoning='deterministic', response_is_due=True, probability=1.0)

        # Create the user prompt with all email messages in human-readable format

        user_prompt = format_emails(emails, style="human", bot_address=bot_address)

        # "analysis": auxiliary task: allows non-reasoning LLMs to think, used only for debugging
        # "assistant_is_next": auxiliary task, affects how "date" is evaluated
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "conversation_analysis",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "analysis": {
                            "type": "string",
                            "description": "Summarize open questions (if any), think step by step: who will answer next?"
                        },
                        "assistant_is_next": {
                            "type": "boolean",
                            "description": "Whether the next message might be send by the agent"
                        },
                        "date": {
                            "type": "string",
                            "description": "Expected date and time of next message in email (RFC 2822) format"
                        }
                    },
                    "required": ["analysis", "assistant_is_next", "date"],
                    "additionalProperties": False
                }
            }
        }

        openrouter_json = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,  # Lower temperature for more deterministic responses
        }

        if model_id in models_supporting_structured_output:
            openrouter_json['response_format'] = response_format
        else:
            print(f"WARNING: schedule_response uses model w/o response_format: {model_id}")

        if verbose:
            print(f"\n\nSystem Prompt:\n{system_prompt}")
            print(f"User Prompt:\n{user_prompt}")

        if DEBUG:
            return {'reasoning': 'DEBUG', 'response_is_due': False, 'probability': 0.5}  # Skip LLM call

        # OpenRouter request
        try:
            response = requests.post(
                self.openrouter_base_url,
                headers=self.openrouter_headers,
                json=openrouter_json,
                timeout=self.llm_timeout
            )
        except Exception as e:
            return dict(error=f"OpenRouter Error: {str(e)}")

        # Handle Errors
        if response.status_code != 200:
            return dict(error=f"Error: {response.status_code} - {response.text}")

        if "choices" not in response.json():
            # Handle errors from LLM provider
            if 'error' in response.json():
                error = response.json()['error']
                print(error['message'] if 'message' in error else error)
                if 'metadata' in error and 'raw' in error['metadata']:
                    print(error['metadata']['raw'])
            else:
                print(response.json())
            return dict(error=f"Error: {response.status_code} - {response.text}")

        try:
            content = response.json()["choices"][0]["message"]["content"].strip()
        except KeyError as e:
            print(f"Error: no message/content found in LLM response {response.json()["choices"][0]}")
            return dict(error=f"Error: {e}")

        # Count input/output tokens, calculate LLM cost
        tokenizer, price_in, price_out = self.get_model_pricing(model_id)
        if tokenizer:
            try:
                encoding = tiktoken.encoding_for_model(tokenizer)
            except Exception:
                print("tiktoken: tokenizer {tokenizer} not supported, using gpt-3.5-turbo instead")
                encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
            num_input_tokens = len(encoding.encode("\n".join([system_prompt, user_prompt])))
            num_output_tokens = len(encoding.encode(content))
            cost = num_input_tokens * price_in + num_output_tokens * price_out
            print(f"Tokens in: {num_input_tokens}, out: {num_output_tokens}, total cost: (USD) {cost}")

        # Parse the JSON structured output
        try:
            result = json.loads(content)
            # Validate the response has the required fields
            if "assistant_is_next" in result and "date" in result:
                return self._evaluate_output(result, now)
            else:
                return dict(error="Invalid response format from LLM")

        except json.JSONDecodeError:
            # If the response isn't valid JSON, try to extract it using regex
            print("WARNING: LLM did not return JSON, trying with regex...")
            assistant_is_next_pattern = r'"assistant_is_next"\s*:\s*(true|false)'
            date_pattern = r'"date"\s*:\s*"([^"]+)"'

            assistant_match = re.search(assistant_is_next_pattern, content, re.IGNORECASE)
            date_match = re.search(date_pattern, content)

            if assistant_match and date_match:
                result = {
                    "assistant_is_next": assistant_match.group(1).lower() == "true",
                    "date": date_match.group(1),
                }
                return self._evaluate_output(result, now)
            else:
                print("ERROR: Also regex failed to match LLM response:")
                print(textwrap.indent(content, '    '))
                return dict(error="Failed to parse LLM response")


    def _evaluate_output(self, result, now=None):
        """
        Validates the output from the LLM and converts it to the expected format.

        Args:
            result (dict): The parsed JSON result from the LLM with 'assistant_is_next' and 'date' fields
            now (datetime, optional): Current datetime. Defaults to datetime.now().

        Returns:
            dict: Dictionary with 'response_is_due', 'probability', and optional 'error' fields
        """
        now = now or datetime.now()

        try:
            analysis = result.get("analysis", "None")

            # Parse the predicted date
            predicted_date_str = result.get("date", "")

            # Try to parse the RFC 2822 format date
            try:
                # email.utils.parsedate_to_datetime can parse RFC 2822 format
                predicted_date = email.utils.parsedate_to_datetime(predicted_date_str)
            except (ValueError, TypeError):
                # If that fails, try a more flexible approach
                try:
                    from dateutil import parser
                    predicted_date = parser.parse(predicted_date_str)
                except (ValueError, ImportError):
                    return dict(error="Invalid date format")

            # DEBUG output
            print(f"\nFields in result: {list(result.keys())}")
            print(f"Analysis: {analysis}")
            print(f"                       predicted DATE: {predicted_date}   SENDER: {'assistant' if result['assistant_is_next'] else 'user'}")

            # Calculate time till scheduled response in minutes
            min_ahead = (predicted_date - now).total_seconds() / 60

            # If assistant is next, respond now or when scheduled, otherwise wait 90 min
            patience = 0 if result.get("assistant_is_next", True) else 90
            if min_ahead + patience <= 0:
                print(f"Deterministic logic: min_ahead ({min_ahead}) + patience ({patience}) <= 0, reponse is due.")  # DEBUG
                return {"response_is_due": True, "probability": 1.0}
            else:
                print(f"Deterministic logic: min_ahead ({min_ahead}) + patience ({patience}) > 0, reponse is not due.")  # DEBUG
                return {"response_is_due": False, "probability": 0.0}

        except Exception as e:
            return dict(error=f"Error validating output: {str(e)}")

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
