import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import google.generativeai as genai
import os
import sqlite3
import json # Moved import json to the top
import re # Import re for regex operations
from dotenv import load_dotenv
from math import ceil # Import ceil for pagination calculations

# Load environment variables from .env file
load_dotenv()

# Configure Gemini API
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("Error: GOOGLE_API_KEY not found in environment variables or .env file.")
    # Exit or handle the error appropriately
genai.configure(api_key=api_key)

app = Flask(__name__)
DATABASE = 'hn_summaries.db'

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                comments_link TEXT,
                score INTEGER,
                num_comments INTEGER,
                article_summary TEXT,
                comments_summary TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Add new columns if they don't exist
        cursor.execute("PRAGMA table_info(articles)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'gemini_is_relevant' not in columns:
            cursor.execute("ALTER TABLE articles ADD COLUMN gemini_is_relevant INTEGER DEFAULT 0")
            print("Added 'gemini_is_relevant' column to 'articles' table.")
        if 'gemini_relevance_score' not in columns:
            cursor.execute("ALTER TABLE articles ADD COLUMN gemini_relevance_score INTEGER DEFAULT 0")
            print("Added 'gemini_relevance_score' column to 'articles' table.")
        conn.commit()
    print("Database initialized.")

HN_BASE_URL = "https://news.ycombinator.com/"
HN_COMMENTS_URL = "https://news.ycombinator.com/item?id="

# No longer a global variable, data will be fetched from DB
# processed_articles = []

def fetch_hacker_news_articles():
    """Fetches top articles from Hacker News."""
    print("Fetching Hacker News articles...")
    print(f"HN_BASE_URL: {HN_BASE_URL}")
    response = requests.get(HN_BASE_URL)
    print(f"HTTP Status Code for HN_BASE_URL: {response.status_code}")
    if response.status_code != 200:
        print(f"Error: Could not fetch Hacker News page. Status code: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    articles = []
    athing_rows = soup.find_all('tr', class_='athing')
    print(f"Found {len(athing_rows)} 'athing' rows.")

    for i, row in enumerate(athing_rows):
        title_tag = row.find('span', class_='titleline').find('a')
        if not title_tag:
            print(f"  Skipping row {i+1}: No title tag found.")
            continue
        title = title_tag.get_text()
        link = title_tag.get('href')
        article_id = row.get('id')
        print(f"  Found article {i+1}: Title='{title}', Link='{link}', ID='{article_id}'")

        comments_link = None
        score = 0
        num_comments = 0
        print(f"  Checking subtext for article ID {article_id}...")

        # Find the next sibling that is a 'tr' tag and contains the 'subtext' class
        subtext_row = None
        for sibling in row.next_siblings:
            if sibling.name == 'tr':
                subtext_row = sibling
                break

        if subtext_row:
            print("    Subtext row found.")
            print(f"    Subtext row HTML: {subtext_row}") # Add this line for debugging
            subtext_td = subtext_row.find('td', class_='subtext') # Correctly find the td with class 'subtext'
            if subtext_td:
                print("      Subtext td found.")
                # The score and comments are inside a span with class 'subline' within the 'subtext' td
                subline_span = subtext_td.find('span', class_='subline')
                if subline_span:
                    print("        Subline span found.")
                    score_span = subline_span.find('span', class_='score') # Search within the subline_span
                    if score_span:
                        score_text = score_span.get_text()
                        print(f"          Score text found: '{score_text}'")
                        try:
                            score = int(score_text.replace(' points', '').strip())
                        except ValueError:
                            print(f"          Could not parse score: '{score_text}'")
                            score = 0
                    else:
                        print("          No score span found.")

                    found_comments_link = False
                    for a_tag in subline_span.find_all('a'): # Search within the subline_span
                        if 'comments' in a_tag.get_text() or 'discuss' in a_tag.get_text():
                            comments_link = HN_BASE_URL + a_tag.get('href')
                            comments_text = a_tag.get_text()
                            print(f"          Comments link found: '{comments_link}', text: '{comments_text}'")
                            found_comments_link = True
                            try:
                                # Extract number of comments, handling "discuss" case and non-digit characters
                                if 'comments' in comments_text:
                                    num_comments = int(re.sub(r'\D', '', comments_text))
                                elif 'discuss' in comments_text:
                                    num_comments = 0 # "discuss" means 0 comments initially
                            except ValueError:
                                print(f"          Could not parse num_comments: '{comments_text}'")
                                num_comments = 0
                            break # Found the comments link, no need to check other a_tags
                    if not found_comments_link:
                        print("          No comments link found in subline span.")
                else:
                    print("        No subline span found within subtext td.")
            else:
                print("      No subtext td found.") # Changed print statement
        else:
            print("    No subtext row found.")
        print(f"  Extracted Score: {score}, Num Comments: {num_comments}")

        articles.append({
            'id': article_id,
            'title': title,
            'link': link,
            'comments_link': comments_link,
            'score': score,
            'num_comments': num_comments
        })
    return articles

def fetch_article_content(url):
    """Fetches the content of an article."""
    try:
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Attempt to extract main content, this is highly dependent on website structure
        # For simplicity, let's just get all paragraph text
        paragraphs = soup.find_all('p')
        text = ' '.join([p.get_text() for p in paragraphs])
        return text if text else soup.get_text() # Fallback to all text if no paragraphs
    except Exception as e:
        print(f"Error fetching article content from {url}: {e}")
        return ""

def fetch_comments_content(comments_link):
    """Fetches the content of comments for an article."""
    if not comments_link:
        return ""
    try:
        response = requests.get(comments_link, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        comments_trees = soup.find_all('table', class_='comment-tree')
        comments_text = []
        for tree in comments_trees:
            for comment_div in tree.find_all('div', class_='commtext'):
                comments_text.append(comment_div.get_text())
        return ' '.join(comments_text)
    except Exception as e:
        print(f"Error fetching comments from {comments_link}: {e}")
        return ""

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

def process_hacker_news_data():
    """
    Fetches, filters, summarizes Hacker News articles and comments.
    Stores the results in the SQLite database.
    """
    articles = fetch_hacker_news_articles()
    print(f"Step 1: Fetched {len(articles)} articles from Hacker News.")
    
    # Batch filter and score using Gemini LLM
    # Import json module
    import json
    relevance_results = batch_filter_and_score_with_gemini(articles)
    
    newly_processed_count = 0
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        for i, article in enumerate(articles):
            article_id = article['id']
            
            # Check if article already exists in DB
            cursor.execute("SELECT article_summary, comments_summary FROM articles WHERE id = ?", (article_id,))
            existing_article = cursor.fetchone()

            if existing_article:
                print(f"  Article '{article['title']}' (ID: {article_id}) already exists in DB. Skipping summarization.")
                # Optionally update other fields if needed, but summaries are kept
                continue

            # Get relevance decision and score from Gemini results
            is_relevant = relevance_results[i]['is_relevant']
            relevance_score = relevance_results[i]['relevance_score']

            print(f"  Article {i+1}: '{article['title']}' (HN Score: {article['score']}, Comments: {article['num_comments']}, Gemini Relevance: {is_relevant}, Gemini Score: {relevance_score})")
            if not is_relevant:
                print(f"  Skipping article {i+1}: '{article['title']}' due to Gemini filter decision (NOT RELEVANT).")
                continue
            else:
                print(f"  Article {i+1}: '{article['title']}' passed Gemini filter (RELEVANT).")

            print(f"Processing new article {i+1}/{len(articles)}: {article['title']}")
            
            article_content = fetch_article_content(article['link'])
            if not article_content:
                print(f"  Skipping article '{article['title']}' due to no article content fetched from {article['link']}.")
                continue
            print(f"  Article content length: {len(article_content)} characters.")

            # Summarize article
            print("  Summarizing article content...")
            article_summary = summarize_text(article_content)
            if article_summary == "Error summarizing content." or article_summary == "No content to summarize.":
                print(f"  Skipping article '{article['title']}' due to error or no content in article summary.")
                continue
            print(f"  Article summary length: {len(article_summary)} characters.")

            # Summarize comments
            print("  Summarizing comments content...")
            comments_content = fetch_comments_content(article['comments_link'])
            if not comments_content:
                print(f"  No comments content fetched for '{article['title']}'.")
                comments_summary = "No comments to summarize." # Assign a default if no comments
            else:
                print(f"  Comments content length: {len(comments_content)} characters.")
                comments_summary = summarize_text(comments_content)
                if comments_summary == "Error summarizing content." or comments_summary == "No content to summarize.":
                    print(f"  Skipping article '{article['title']}' due to error or no content in comments summary.")
                    continue
                print(f"  Comments summary length: {len(comments_summary)} characters.")

            # Insert new article into DB
            cursor.execute('''
                INSERT INTO articles (id, title, link, comments_link, score, num_comments, article_summary, comments_summary, gemini_is_relevant, gemini_relevance_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                article['id'],
                article['title'],
                article['link'],
                article['comments_link'],
                article['score'], # Use original HN score here
                article['num_comments'],
                article_summary,
                comments_summary,
                1 if is_relevant else 0, # Store boolean as integer
                relevance_score
            ))
            conn.commit()
            newly_processed_count += 1
            print(f"  Article '{article['title']}' (ID: {article_id}) successfully processed and saved to DB.")
    print(f"Finished processing. Newly processed and saved articles: {newly_processed_count}.")

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.add_job(func=process_hacker_news_data, trigger="interval", hours=1)
scheduler.start()

# Initial data load - ensure it runs once at startup
# The scheduler will handle subsequent runs
process_hacker_news_data() 


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def data():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int) # Default to 10 items per page

    # Validate per_page to be one of the allowed values
    allowed_per_page = [10, 20, 50, 100]
    if per_page not in allowed_per_page:
        per_page = 10 # Default to 10 if an invalid value is provided

    offset = (page - 1) * per_page

    articles_from_db = []
    total_articles = 0
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM articles")
        total_articles = cursor.fetchone()[0]

        cursor.execute("SELECT * FROM articles ORDER BY timestamp DESC LIMIT ? OFFSET ?", (per_page, offset))
        articles_from_db = [dict(row) for row in cursor.fetchall()]
    
    total_pages = ceil(total_articles / per_page)

    print(f"Data route: Retrieved {len(articles_from_db)} articles from DB (Page: {page}, Per Page: {per_page}). Total articles: {total_articles}, Total pages: {total_pages}")
    return jsonify({
        'articles': articles_from_db,
        'total_articles': total_articles,
        'total_pages': total_pages,
        'current_page': page,
        'per_page': per_page
    })

if __name__ == '__main__':
    init_db() # Initialize database when the app starts
    # Ensure templates directory exists
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, use_reloader=False) # use_reloader=False because of APScheduler
