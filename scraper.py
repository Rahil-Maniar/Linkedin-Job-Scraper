import os
import time
import random
import csv
from playwright.sync_api import sync_playwright

# --- Configuration ---
# DO NOT HARDCODE YOUR CREDENTIALS HERE
# These are loaded from GitHub Secrets
LINKEDIN_EMAIL = os.environ.get('LINKEDIN_USER')
LINKEDIN_PASSWORD = os.environ.get('LINKEDIN_PASS')

# List of search terms you are interested in
SEARCH_TERMS = [
    "product manager #hiring",
    "software engineer #hiring remote",
    "data analyst #hiring #usa",
    "UX designer #hiring"
]

# --- Helper Functions ---

def construct_search_url(search_term: str) -> str:
    """Constructs a LinkedIn search URL for the latest posts in the past 24 hours."""
    # URL encodes the search term to handle spaces and special characters
    from urllib.parse import quote
    encoded_term = quote(search_term)
    # This URL structure filters for Posts, Past 24 hours, and sorts by Latest
    return f"https://www.linkedin.com/search/results/content/?datePosted=%22past-24h%22&keywords={encoded_term}&sortBy=%22date_posted%22"

def get_existing_post_urls(filename="jobs.csv"):
    """Reads the CSV file and returns a set of all post URLs already saved."""
    post_urls = set()
    try:
        with open(filename, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            # Skip header row if it exists
            try:
                next(reader) 
            except StopIteration:
                pass # File is empty
            for row in reader:
                if len(row) > 2: # Check if row has the post_url column
                    post_urls.add(row[2])
    except FileNotFoundError:
        # If the file doesn't exist yet, return an empty set
        pass
    return post_urls

# --- Main Script Logic ---

print("Starting LinkedIn scraper...")

# Add a random delay to make the script less predictable
sleep_time = random.randint(30, 300) # Sleep for 30 seconds to 5 minutes
print(f"Waiting for {sleep_time} seconds before starting...")
time.sleep(sleep_time)

# Load existing post URLs to avoid duplicates
existing_urls = get_existing_post_urls()
print(f"Found {len(existing_urls)} existing jobs in jobs.csv. These will be skipped.")

new_jobs_found = 0

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True) # Use headless=False to watch it run locally
    page = browser.new_page()

    try:
        # --- Login ---
        print("Logging in...")
        page.goto('https://www.linkedin.com/login')
        page.locator('input#username').fill(LINKEDIN_EMAIL)
        page.locator('input#password').fill(LINKEDIN_PASSWORD)
        page.locator('button[type="submit"]').click()

        # Wait for the main feed to load to confirm login was successful
        page.wait_for_selector('div.feed-identity-module', timeout=30000)
        print("Login successful.")

        # --- Scrape Search Terms ---
        for term in SEARCH_TERMS:
            print(f"\nSearching for: '{term}'")
            search_url = construct_search_url(term)
            page.goto(search_url)

            # Scroll down to load posts
            for _ in range(5): # Scroll 5 times to load a good number of posts
                page.keyboard.press('End')
                time.sleep(random.uniform(2, 4)) # Wait for content to load

            # Find all post elements on the page
            posts = page.locator('div.feed-shared-update-v2').all()
            print(f"Found {len(posts)} potential posts on the page.")

            for post in posts:
                try:
                    # Extract the permanent link to the post
                    post_url_element = post.locator('a.feed-shared-update-v2__control-menu')
                    post_urn = post_url_element.get_attribute('id')
                    post_id = post_urn.split(':')[-1]
                    post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{post_id}"

                    if post_url not in existing_urls:
                        author_element = post.locator('span.feed-shared-actor__name').first
                        author_name = author_element.inner_text().strip()

                        content_element = post.locator('div.update-components-text').first
                        content_text = content_element.inner_text().strip().replace('\n', ' ')

                        # Save to CSV
                        with open("jobs.csv", mode='a', newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            # Write header if the file is new/empty
                            if f.tell() == 0:
                                writer.writerow(["Author", "Content", "PostURL"])
                            writer.writerow([author_name, content_text, post_url])
                        
                        existing_urls.add(post_url) # Add to our set to avoid re-saving in this session
                        new_jobs_found += 1
                        print(f"  -> SAVED: New job from {author_name}")

                except Exception as e:
                    # This handles cases where a post is not a standard job post (e.g., a poll)
                    # print(f"  -> SKIPPED: Could not parse a post. Error: {e}")
                    pass

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        # Take a screenshot on error for debugging in GitHub Actions
        page.screenshot(path='error_screenshot.png')

    finally:
        browser.close()

print(f"\nScraping complete. Found and saved {new_jobs_found} new jobs.")
