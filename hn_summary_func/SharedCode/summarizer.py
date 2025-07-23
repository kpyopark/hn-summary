import google.generativeai as genai
import os
import json

def configure_gemini():
    """Configures the Gemini API with the API key from environment variables."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Error: GOOGLE_API_KEY not found in environment variables or .env file.")
    genai.configure(api_key=api_key)

def summarize_text(text, max_length=150):
    """Summarizes text using Google Gemini API."""
    if not text:
        print("Summarize_text: No content to summarize.")
        return "No content to summarize."
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"Summarize the following text concisely, aiming for around {max_length} words:\n\n{text}"
        response = model.generate_content(prompt)
        summary = response.text
        print(f"Summarize_text: Generated summary (first 50 chars): {summary[:50]}...")
        return summary
    except Exception as e:
        print(f"Error summarizing text with Gemini: {e}")
        return "Error summarizing content."

def batch_filter_and_score_with_gemini(articles):
    """
    Uses Gemini LLM to filter and assign a relevance score to a batch of articles.
    Returns a list of dictionaries, each with 'is_relevant' (bool) and 'relevance_score' (int).
    """
    if not articles:
        return []

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt_parts = [
            "For each Hacker News article provided below, determine if it is highly relevant to AI/ML, LLM architecture, mathematical concepts, or other deeply technical subjects, and important enough to be summarized. "
            "For each article, output a JSON object on a new line with two keys: 'is_relevant' (boolean, true if relevant, false otherwise) and 'relevance_score' (integer from 1 to 10, where 10 is most relevant/important). "
            "Ensure the output is valid JSON and strictly follows the order of input articles. Do not add any other text or explanations outside the JSON objects.\n\n"
        ]
        for i, article in enumerate(articles):
            prompt_parts.append(f"Article {i+1}: Title: '{article['title']}', Comments: {article['num_comments']}\n")
        
        prompt = "".join(prompt_parts)
        response = model.generate_content(prompt)
        
        # Clean the response text by removing markdown code block wrappers
        cleaned_response_text = response.text.strip()
        if cleaned_response_text.startswith('```json') and cleaned_response_text.endswith('```'):
            cleaned_response_text = cleaned_response_text[len('```json'):-len('```')].strip()
        
        results = []
        for line in cleaned_response_text.split('\n'):
            if line.strip(): # Ensure line is not empty
                try:
                    json_obj = json.loads(line)
                    results.append(json_obj)
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON from Gemini response: {e}. Line: '{line}'")
                    results.append({'is_relevant': False, 'relevance_score': 0}) # Default to not relevant
        
        print(f"Gemini batch filter and score results: {results}")
        return results
    except Exception as e:
        print(f"Error using Gemini for batch filtering and scoring: {e}")
        return [{'is_relevant': False, 'relevance_score': 0}] * len(articles) # Default to not relevant for all if error
