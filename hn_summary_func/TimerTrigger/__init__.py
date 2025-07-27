import datetime
import logging
import azure.functions as func

from ..SharedCode import hn_scraper, summarizer, db_operations

def main(mytimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.datetime.utcnow().replace(
        tzinfo=datetime.timezone.utc).isoformat()

    if mytimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Python timer trigger function ran at %s', utc_timestamp)

    try:
        # Configure Gemini API
        summarizer.configure_gemini()

        # 1. Fetch articles from Hacker News
        articles = hn_scraper.fetch_hacker_news_articles()
        logging.info(f"Step 1: Fetched {len(articles)} articles from Hacker News.")

        # 2. Batch filter and score using Gemini LLM
        relevance_results = summarizer.batch_filter_and_score_with_gemini(articles)

        # 3. Process and store relevant articles
        newly_processed_count = 0
        for i, article in enumerate(articles):
            # Get relevance decision and score from Gemini results
            is_relevant = relevance_results[i]['is_relevant']
            relevance_score = relevance_results[i]['relevance_score']

            logging.info(f"  Article {i+1}: '{article['title']}' (HN Score: {article['score']}, Comments: {article['num_comments']}, Gemini Relevance: {is_relevant}, Gemini Score: {relevance_score})")
            if not is_relevant:
                logging.info(f"  Skipping article {i+1}: '{article['title']}' due to Gemini filter decision (NOT RELEVANT).")
                continue
            else:
                logging.info(f"  Article {i+1}: '{article['title']}' passed Gemini filter (RELEVANT).")

            logging.info(f"Processing new article {i+1}/{len(articles)}: {article['title']}")
            
            article_content = hn_scraper.fetch_article_content(article['link'])
            if not article_content:
                logging.info(f"  Skipping article '{article['title']}' due to no article content fetched from {article['link']}.")
                continue
            
            # Summarize article
            article_summary = summarizer.summarize_text(article_content)
            if article_summary == "Error summarizing content." or article_summary == "No content to summarize.":
                logging.info(f"  Skipping article '{article['title']}' due to error or no content in article summary.")
                continue

            # Summarize comments
            comments_content = hn_scraper.fetch_comments_content(article['comments_link'])
            if not comments_content:
                comments_summary = "No comments to summarize."
            else:
                comments_summary = summarizer.summarize_text(comments_content)
                if comments_summary == "Error summarizing content." or comments_summary == "No content to summarize.":
                    logging.info(f"  Skipping article '{article['title']}' due to error or no content in comments summary.")
                    continue
            
            # Prepare article data for database
            article_data = {
                'id': article['id'],
                'title': article['title'],
                'link': article['link'],
                'comments_link': article['comments_link'],
                'score': article['score'],
                'num_comments': article['num_comments'],
                'article_summary': article_summary,
                'comments_summary': comments_summary,
                'gemini_is_relevant': is_relevant,
                'gemini_relevance_score': relevance_score,
                'timestamp': utc_timestamp
            }

            db_operations.save_article(article_data)
            logging.info(f"  Article '{article['title']}' (ID: {article['id']}) successfully processed and saved to Cosmos DB.")
            newly_processed_count += 1

        logging.info(f"Finished processing. Newly processed and saved articles: {newly_processed_count}.")

    except Exception as e:
        logging.error(f"An error occurred during the execution of the timer trigger: {e}")
