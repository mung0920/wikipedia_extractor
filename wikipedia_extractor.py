import datetime  # <-- NOT in the slides (needed for the required timestamp)
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://en.wikipedia.org/wiki/"
HEADERS = {"User-Agent": "WikipediaArticleExtractor/1.0 (student project)"}


class ArticleNotFoundError(Exception):
    """Raised when a topic has no matching Wikipedia article."""


def clean_text(text):
    """Remove [..] citation markers using a for loop and if/elif only."""
    result = ""
    inside = False
    for char in text:
        if char == "[":
            inside = True
        elif char == "]":
            inside = False
        else:
            if inside == False:
                result += char
    return result.strip()


def build_url(topic):
    """Turn the typed topic into a Wikipedia article URL."""
    return BASE_URL + topic.strip().replace(" ", "_")


def fetch_page(topic):
    """Download one article and return a WikipediaArticle object."""
    url = build_url(topic)
    response = requests.get(url, headers=HEADERS, timeout=10)

    if response.status_code == 404:
        raise ArticleNotFoundError(
            "No Wikipedia article was found for '" + topic + "'."
        )

    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    page_title = soup.find("title").get_text(strip=True)   # .find() usage
    return WikipediaArticle(page_title, url, soup)


class WikipediaArticle:
    """One Wikipedia article plus the sections we can extract."""

    def __init__(self, title, url, soup):
        self.title = title
        self.url = url
        self.soup = soup
        self.sections = self.collect_sections()

    def collect_sections(self):
        """Collect the article's top-level (h2) sections into a list."""
        sections = []
        for heading in self.soup.find_all("h2"):           # .find_all() usage
            name = heading.get_text(strip=True)
            if name != "":
                sections.append({"title": name, "heading": heading})
        return sections

    def read_section(self, section):
        """Turn one section into readable text."""
        title = section["title"]
        lines = []
        lines.append("")
        lines.append(title.upper())
        lines.append("-" * len(title))

        # navigate the tag tree with next_siblings (covered in Session 2)
        for element in section["heading"].next_siblings:
            tag = getattr(element, "name", None)  # built-in helper

            if tag == "h2":
                break
            if tag == "h3" or tag == "h4" or tag == "h5" or tag == "h6":
                sub = clean_text(element.get_text(strip=True))
                if sub != "":
                    lines.append("  " + sub)
            elif tag == "p":
                text = clean_text(element.get_text(" ", strip=True))
                if text != "":
                    lines.append(text)
            elif tag == "ul" or tag == "ol":
                for item in element.find_all("li"):
                    text = clean_text(item.get_text(" ", strip=True))
                    if text != "":
                        lines.append("  - " + text)
            elif tag == "table":
                for row in element.find_all("tr"):
                    values = []
                    for cell in row.find_all(["th", "td"]):
                        value = clean_text(cell.get_text(" ", strip=True))
                        if value != "":
                            values.append(value)
                    if len(values) > 0:
                        lines.append("  | " + " | ".join(values))
        return "\n".join(lines)

    def read_sections(self, numbers):
        """Read the chosen sections (1-based numbers) into one string."""
        lines = []
        lines.append("Article title: " + self.title)
        lines.append("Source URL: " + self.url)
        lines.append(
            "Extracted on: "
            + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )  # <-- NOT in the slides, required by the brief
        lines.append("Licence: CC BY-SA 4.0")
        lines.append("=" * 60)
        for number in numbers:
            section = self.sections[number - 1]
            lines.append(self.read_section(section))
        return "\n".join(lines)


def parse_selection(raw, count):
    """Read the choice: 'all', single numbers, comma lists and ranges."""
    text = raw.strip().lower()
    chosen = []

    if text == "all":
        for number in range(1, count + 1):
            chosen.append(number)
        return chosen

    for part in text.split(","):
        part = part.strip()
        if part == "":
            continue

        if "-" in part:
            bounds = part.split("-")
            if len(bounds) != 2:
                raise ValueError("'" + part + "' is not a valid range")
            first = bounds[0].strip()
            second = bounds[1].strip()
            if first.isdigit() == False or second.isdigit() == False:
                raise ValueError("'" + part + "' is not a valid range")
            start = int(first)
            end = int(second)
            if start > end:
                raise ValueError("'" + part + "' starts after it ends")
            number = start
            while number <= end:
                if number not in chosen:
                    chosen.append(number)
                number += 1
        else:
            if part.isdigit() == False:
                raise ValueError("'" + part + "' is not a number")
            number = int(part)
            if number not in chosen:
                chosen.append(number)

    if len(chosen) == 0:
        raise ValueError("no section numbers were given")

    for number in chosen:
        if number < 1 or number > count:
            raise ValueError(
                "section " + str(number) + " is out of range (1-" + str(count) + ")"
            )

    chosen.sort()
    return chosen


def make_filename(title):
    """Build a simple .txt filename from the article title."""
    safe = ""
    for char in title:
        if char.isalnum() or char == " " or char == "_" or char == "-":
            safe += char
    safe = safe.strip().replace(" ", "_")
    if safe == "":
        safe = "wikipedia_article"
    return safe + ".txt"


def ask_yes_no(question):
    """Ask a yes/no question until the answer is valid."""
    while True:
        answer = input(question).strip().lower()
        if answer == "y" or answer == "yes":
            return True
        if answer == "n" or answer == "no":
            return False
        print("Please type 'y' or 'n'.")


def create_empty_file(name):
    """Try to create a new file; return True only if it did not exist."""
    try:
        handle = open(name, "x", encoding="utf-8")  # 'x' fails if file exists
        handle.close()
        return True
    except FileExistsError:
        return False


def save_content(article, content):
    """Save the text, handling an existing file name."""
    filename = make_filename(article.title)

    if create_empty_file(filename):
        target = filename
    else:
        if ask_yes_no("'" + filename + "' already exists. Overwrite? (y/n): "):
            target = filename
        else:
            base = filename[:-4]          # slice off ".txt"
            counter = 1
            while True:
                target = base + "_" + str(counter) + ".txt"
                if create_empty_file(target):
                    break
                counter += 1

    try:
        handle = open(target, "w", encoding="utf-8")
        handle.write(content)
        handle.close()
    except OSError as error:
        print("Could not save the file: " + str(error))
        return
    print("Content saved to '" + target + "'.")


def prompt_topic():
    """Ask for a topic and try to download the article (with retries)."""
    while True:
        topic = input("Enter a topic to search (or 'back' to return): ").strip()
        if topic.lower() == "back":
            return None
        if topic == "":
            print("The topic cannot be empty. Please try again.")
            continue
        try:
            article = fetch_page(topic)
            print("Found article: " + article.title)
            return article
        except ArticleNotFoundError as error:
            print(str(error) + " Please try another topic.")
        except requests.exceptions.RequestException as error:
            print("Network or HTTP error: " + str(error))
        except ValueError as error:
            print("Could not read the page: " + str(error))


def display_sections(article):
    """Print the numbered list of top-level sections."""
    if len(article.sections) == 0:
        print("No top-level sections were found for this article.")
        return
    print("")
    print("Available sections:")
    number = 1
    for section in article.sections:
        print("  " + str(number) + ". " + section["title"])
        number += 1


def prompt_selection(count):
    """Ask for section numbers with validation and retry."""
    while True:
        raw = input(
            "Enter section numbers (e.g. 1,3,5-7 or 'all'), "
            "or 'back' to return: "
        )
        if raw.strip().lower() == "back":
            return None
        try:
            return parse_selection(raw, count)
        except ValueError as error:
            print("Invalid selection: " + str(error) + ". Please try again.")


def extract_and_save(article):
    """Guide the user through selecting sections and saving them."""
    if len(article.sections) == 0:
        print("This article has no sections to extract.")
        return
    display_sections(article)
    numbers = prompt_selection(len(article.sections))
    if numbers is None:
        return
    content = article.read_sections(numbers)
    save_content(article, content)


def main():
    """Show the console menu and handle the user's choices."""
    print("=" * 60)
    print("Wikipedia Article Extractor")
    print("=" * 60)
    print("Search a topic, choose the sections you want and save them to a .txt file.")

    current_article = None
    while True:
        print("")
        print("--- Main Menu ---")
        print("1. Search for a Wikipedia topic")
        print("2. View available sections")
        print("3. Extract sections and save to a .txt file")
        print("4. Exit")
        choice = input("Enter your choice (1-4): ").strip()

        if choice == "1":
            article = prompt_topic()
            if article is not None:
                current_article = article
        elif choice == "2":
            if current_article is None:
                print("Please search for a topic first (option 1).")
            else:
                display_sections(current_article)
        elif choice == "3":
            if current_article is None:
                print("Please search for a topic first (option 1).")
            else:
                extract_and_save(current_article)
        elif choice == "4":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter a number from 1 to 4.")


if __name__ == "__main__":
    main() 
