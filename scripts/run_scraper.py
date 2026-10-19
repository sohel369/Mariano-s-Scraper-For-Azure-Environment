import os
import sys
import argparse
import json

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.scraper import MarianoProductionScraper

def main():
    parser = argparse.ArgumentParser(description="Run Mariano's Production Scraper")
    parser.add_argument("--zipcode", type=str, default="60601", help="Target Mariano's store ZIP code")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages to scrape per subcategory")
    args = parser.parse_args()

    scraper = MarianoProductionScraper()
    stats = scraper.execute_run(zipcode=args.zipcode, max_pages_override=args.max_pages)
    
    print("\n" + "="*50)
    print("MARIANO'S RUN SUMMARY STATISTICS:")
    print("="*50)
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    main()
