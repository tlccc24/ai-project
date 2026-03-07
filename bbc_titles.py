import requests
from bs4 import BeautifulSoup
import csv

def fetch_bbc_homepage():
    url = 'https://www.bbc.co.uk'
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def extract_titles(html):
    soup = BeautifulSoup(html, 'html.parser')
    titles = [a.get_text() for a in soup.find_all('a', href=True)]
    return titles

def save_titles_to_csv(titles, filename='bbc_titles.csv'):
    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Title'])
        for title in titles:
            writer.writerow([title])

def main():
    html = fetch_bbc_homepage()
    titles = extract_titles(html)
    save_titles_to_csv(titles)
    print(f"Titles saved to bbc_titles.csv")

if __name__ == '__main__':
    main()
