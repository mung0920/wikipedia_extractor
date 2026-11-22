"""
ISOM3400 Individual Assignment
Wikipedia Article Extractor
--------------------------------------------------------------
A console application that searches Wikipedia, lists an article's
top-level sections, extracts selected sections, and saves the
result to a readable .txt file.
"""

import datetime
import os
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

BASE_URL = "https://en.wikipedia.org/wiki/"
API_URL = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "WikipediaArticleExtractor/1.0 (student project)"
}

TIMEOUT = 10
LICENCE = "CC BY-SA 4.0"

# Matches common inline citation markers such as [1], [23], or [a]
CITATION_RE = re.compile(r"\[\d+\]|\[[a-z]\]", re.IGNORECASE)


# ----------------------------------------------------------------------
# Custom exception
# ----------------------------------------------------------------------

class ArticleNotFoundError(Exception):
    """Raised when a topic does not match a Wikipedia article."""


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------

def clean_text(text):
    """Remove citation markers and reduce whitespace to single spaces."""
    text = CITATION_RE.sub("", text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def search_wikipedia(topic):
    """
    Search Wikipedia and return the best-matching article title.

    Returns None when no article is found.
    """
    params = {
        "action": "opensearch",
        "search": topic,
        "limit": 1,
        "namespace": 0,
        "format": "json",
    }

    response = requests.get(
        API_URL,
        params=params,
        headers=HEADERS,
        timeout=TIMEOUT
    )
    response.raise_for_status()

    try:
        data = response.json()

        if not isinstance(data, list) or len(data) < 2:
            raise ValueError("Wikipedia returned an unexpected API response.")

        titles = data[1]

        if not isinstance(titles, list):
            raise ValueError("Wikipedia returned an unexpected title list.")

    except (ValueError, IndexError, TypeError) as error:
        raise ValueError(
            "Wikipedia returned an invalid API response."
        ) from error

    return titles[0] if titles else None


def fetch_page(topic):
    """
    Fetch and parse a Wikipedia article.

    Returns a WikipediaArticle object.
    """
    title = search_wikipedia(topic)

    if title is None:
        raise ArticleNotFoundError(
            f"No Wikipedia article was found for '{topic}'."
        )

    # Quote the title so spaces, punctuation, and Unicode characters
    # are handled safely in the URL.
    encoded_title = quote(title.replace(" ", "_"), safe="")
    url = BASE_URL + encoded_title

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    if response.status_code == 404:
        raise ArticleNotFoundError(
            f"The article '{title}' could not be found."
        )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    return WikipediaArticle(title, url, soup)


# ----------------------------------------------------------------------
# Wikipedia article class
# ----------------------------------------------------------------------

class WikipediaArticle:
    """Represents one Wikipedia article and its extracted sections."""

    def __init__(self, title, url, soup):
        self.title = title
        self.url = url
        self.soup = soup
        self.content = self._locate_content()
        self.sections = self._build_sections()

    # ------------------------------------------------------------------
    # Locating and collecting sections
    # ------------------------------------------------------------------

    def _locate_content(self):
        """Find the HTML container holding the article body."""

        # Required .find() usage
        container = self.soup.find("div", id="mw-content-text")

        if container is None:
            raise ValueError("Could not locate the article content.")

        parser_output = container.find(
            "div",
            class_="mw-parser-output"
        )

        return parser_output if parser_output else container

    def _build_sections(self):
        """Collect the article's top-level h2 sections."""

        sections = []

        # Required .find_all() usage
        for heading in self.content.find_all("h2"):
            title = clean_text(
                heading.get_text(" ", strip=True)
            )

            # Some Wikipedia layouts may include an [edit] label.
            title = re.sub(
                r"\s*\[edit\]\s*$",
                "",
                title,
                flags=re.IGNORECASE
            )

            if title:
                sections.append({
                    "title": title,
                    "heading": heading
                })

        return sections

    # ------------------------------------------------------------------
    # Section extraction
    # ------------------------------------------------------------------

    def _extract_section(self, section):
        """Convert one selected section into readable plain text."""

        title = section["title"]
        heading = section["heading"]

        lines = [
            "",
            title.upper(),
            "-" * max(len(title), 3)
        ]

        # next_elements is used because Wikipedia may place headings
        # inside wrapper div elements. Extraction stops at the next h2.
        for element in heading.next_elements:
            name = getattr(element, "name", None)

            # Stop at the next top-level section.
            if name == "h2":
                break

            # Subheadings
            if name in ("h3", "h4", "h5", "h6"):
                subheading = clean_text(
                    element.get_text(" ", strip=True)
                )

                subheading = re.sub(
                    r"\s*\[edit\]\s*$",
                    "",
                    subheading,
                    flags=re.IGNORECASE
                )

                if subheading:
                    lines.append(f"\n  {subheading}")

            # Paragraphs
            elif name == "p":
                # Paragraphs inside tables or list items are handled by
                # their table/list extraction code.
                if element.find_parent(["table", "li"]) is not None:
                    continue

                text = clean_text(
                    element.get_text(" ", strip=True)
                )

                if text:
                    lines.append(text)

            # Ordered and unordered lists
            elif name in ("ul", "ol"):
                # Skip nested lists because the outer list will include
                # their text.
                if element.find_parent(["ul", "ol", "table"]) is not None:
                    continue

                for list_item in element.find_all(
                    "li",
                    recursive=False
                ):
                    item = clean_text(
                        list_item.get_text(" ", strip=True)
                    )

                    if item:
                        lines.append(f"  - {item}")

            # Tables
            elif name == "table":
                # Skip tables nested inside other tables.
                if element.find_parent("table") is not None:
                    continue

                classes = element.get("class") or []

                # Infoboxes and navigation tables are usually not useful
                # as section content.
                if "infobox" in classes or "navbox" in classes:
                    continue

                for row in element.find_all("tr"):
                    cells = [
                        clean_text(cell.get_text(" ", strip=True))
                        for cell in row.find_all(
                            ["th", "td"],
                            recursive=False
                        )
                    ]

                    cells = [cell for cell in cells if cell]

                    if cells:
                        lines.append("  | " + " | ".join(cells))

        return "\n".join(lines)

    def extract_sections(self, indices):
        """
        Extract several sections using 1-based section numbers.

        Returns all extracted sections as one text block.
        """
        timestamp = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        blocks = [
            f"Article title: {self.title}",
            f"Source URL: {self.url}",
            f"Extracted on: {timestamp}",
            f"Licence: {LICENCE}",
            "=" * 60,
        ]

        for index in indices:
            section = self.sections[index - 1]
            blocks.append(self._extract_section(section))

        return "\n".join(blocks)


# ----------------------------------------------------------------------
# Input parsing and validation
# ----------------------------------------------------------------------

def parse_selection(raw, count):
    """
    Parse section selections.

    Accepted examples:
        all
        1
        1,3,5
        2-5
        1,3-5,8
    """
    text = raw.strip().lower()

    if text == "all":
        return list(range(1, count + 1))

    chosen = set()

    for part in text.split(","):
        part = part.strip()

        if not part:
            continue

        if "-" in part:
            bounds = part.split("-")

            if (
                len(bounds) != 2
                or not all(bound.strip().isdigit() for bound in bounds)
            ):
                raise ValueError(f"'{part}' is not a valid range")

            start = int(bounds[0].strip())
            end = int(bounds[1].strip())

            if start > end:
                raise ValueError(
                    f"'{part}' has a larger start than end"
                )

            chosen.update(range(start, end + 1))

        else:
            if not part.isdigit():
                raise ValueError(f"'{part}' is not a number")

            chosen.add(int(part))

    if not chosen:
        raise ValueError("no section numbers were provided")

    for number in chosen:
        if number < 1 or number > count:
            raise ValueError(
                f"section {number} is out of range (1-{count})"
            )

    return sorted(chosen)


def make_filename(title):
    """Create a safe .txt filename from the article title."""

    safe_title = re.sub(
        r"[^A-Za-z0-9 _-]",
        "",
        title
    ).strip()

    safe_title = re.sub(r"\s+", "_", safe_title)

    if not safe_title:
        safe_title = "wikipedia_article"

    return safe_title + ".txt"


def choose_unique_filename(filename):
    """
    Return a non-conflicting filename.

    Example:
        Python.txt
        Python_1.txt
        Python_2.txt
    """
    root, extension = os.path.splitext(filename)
    counter = 1

    while True:
        candidate = f"{root}_{counter}{extension}"

        if not os.path.exists(candidate):
            return candidate

        counter += 1


# ----------------------------------------------------------------------
# Console prompts
# ----------------------------------------------------------------------

def prompt_overwrite(filename):
    """Ask whether an existing file should be overwritten."""

    while True:
        answer = input(
            f"'{filename}' already exists. Overwrite? (y/n): "
        ).strip().lower()

        if answer in ("y", "yes"):
            return True

        if answer in ("n", "no"):
            return False

        print("Please type 'y' or 'n'.")


def prompt_selection(count):
    """Ask the user to select one or more sections."""

    while True:
        raw = input(
            "Enter section numbers "
            "(e.g. 1,3,5-7 or 'all'), "
            "or 'back' to return: "
        ).strip()

        if raw.lower() == "back":
            return None

        try:
            return parse_selection(raw, count)

        except ValueError as error:
            print(
                f"Invalid selection: {error}. "
                "Please try again."
            )


def prompt_topic():
    """Ask for a topic and attempt to download its article."""

    while True:
        topic = input(
            "Enter a topic to search (or 'back'): "
        ).strip()

        if topic.lower() == "back":
            return None

        if not topic:
            print(
                "The topic cannot be empty. "
                "Please try again."
            )
            continue

        try:
            article = fetch_page(topic)
            print(f"Found article: {article.title}")
            return article

        except ArticleNotFoundError as error:
            print(f"{error} Please try a different topic.")

        except requests.exceptions.Timeout:
            print(
                "The request timed out. "
                "Please check your connection and try again."
            )

        except requests.exceptions.ConnectionError:
            print(
                "Could not connect to Wikipedia. "
                "Please check your internet connection."
            )

        except requests.exceptions.HTTPError as error:
            print(f"Wikipedia returned an HTTP error: {error}")

        except requests.exceptions.RequestException as error:
            print(f"Network error: {error}")

        except ValueError as error:
            print(f"Could not parse the page: {error}")


# ----------------------------------------------------------------------
# Display and file-saving functions
# ----------------------------------------------------------------------

def display_sections(article):
    """Display the numbered list of top-level sections."""

    if not article.sections:
        print("No top-level sections were found for this article.")
        return

    print("\nAvailable sections:")

    for index, section in enumerate(
        article.sections,
        start=1
    ):
        print(f"  {index}. {section['title']}")


def save_content(article, content):
    """Save extracted content while handling filename collisions."""

    filename = make_filename(article.title)

    if os.path.exists(filename):
        if prompt_overwrite(filename):
            target = filename
        else:
            target = choose_unique_filename(filename)
            print(f"A new filename will be used: '{target}'")
    else:
        target = filename

    try:
        with open(
            target,
            "w",
            encoding="utf-8"
        ) as file:
            file.write(content)

    except PermissionError:
        print(
            "Permission denied. The file could not be created "
            "in this location."
        )
        return False

    except OSError as error:
        print(f"Error saving the file: {error}")
        return False

    print(f"Content saved successfully to '{target}'.")
    return True


def extract_and_save(article):
    """Guide the user through extraction and saving."""

    if not article.sections:
        print("This article has no sections to extract.")
        return

    display_sections(article)

    selection = prompt_selection(
        len(article.sections)
    )

    if selection is None:
        print("Returning to the main menu.")
        return

    content = article.extract_sections(selection)
    save_content(article, content)


# ----------------------------------------------------------------------
# Main program
# ----------------------------------------------------------------------

def show_welcome():
    """Display the program welcome message."""

    print("=" * 60)
    print(
        " Welcome to the Wikipedia Article Extractor! ".center(
            60,
            "="
        )
    )
    print("=" * 60)
    print("This tool lets you search for a Wikipedia topic,")
    print("view its top-level sections, extract selected sections,")
    print("and save the extracted content to a .txt file.")


def main():
    """Run the console-based main menu."""

    show_welcome()

    current_article = None

    while True:
        print("\n--- Main Menu ---")
        print("1. Search for a Wikipedia topic")
        print("2. View available sections")
        print("3. Extract sections and save to a .txt file")
        print("4. Exit")

        choice = input(
            "Enter your choice (1-4): "
        ).strip()

        if choice == "1":
            article = prompt_topic()

            if article is not None:
                current_article = article

        elif choice == "2":
            if current_article is None:
                print(
                    "Please search for a topic first "
                    "(option 1)."
                )
            else:
                display_sections(current_article)

        elif choice == "3":
            if current_article is None:
                print(
                    "Please search for a topic first "
                    "(option 1)."
                )
            else:
                extract_and_save(current_article)

        elif choice == "4":
            print(
                "Thank you for using the Wikipedia "
                "Article Extractor. Goodbye!"
            )
            break

        else:
            print(
                "Invalid choice. Please enter a number "
                "from 1 to 4."
            )


if __name__ == "__main__":
    main()
    