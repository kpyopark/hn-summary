import requests
from bs4 import BeautifulSoup
import re

HN_BASE_URL = "https://news.ycombinator.com/"

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
