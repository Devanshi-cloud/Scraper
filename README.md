# SquareYards Real Estate Scraper

A robust Python-based web scraper designed to extract ready-to-move project data from SquareYards.com using Selenium and BeautifulSoup. The scraped information, including apartment details, prices, photos, and amenities, is efficiently stored in a MongoDB database. This scraper handles dynamic content loading and pagination.

## Table of Contents

-   [Features](#features)
-   [Technologies Used](#technologies-used)
-   [Setup and Installation](#setup-and-installation)
-   [Configuration](#configuration)
-   [How to Run](#how-to-run)

## Features

* **Dynamic Content Handling**: Utilizes Selenium to interact with the webpage, scroll, and handle JavaScript-loaded content.
* **Detailed Data Extraction**: Scrapes essential information such as apartment names, locations, price ranges, photo URLs, listing URLs, Location Coordinates, Cost Per Sqrft, No. of Units, Total Area and comprehensive amenities.
     * **Sidenote on Price Data**: In the scraped price data, a value of `-1` for either Minimum Price or Maximum Price indicates that the original listing displayed "Price On Request" rather than a specific numeric value.
* **Pagination Support**: Automates navigation through multiple search results pages to gather extensive data.
* **Amenity Scraping**: Implements advanced logic to open and scrape amenities from modal pop-ups on individual detail pages.
* **MongoDB Integration**: Stores scraped data in a MongoDB collection, including checks to prevent duplicate entries.
* **Time-based Execution Limit**: Allows setting a maximum run duration to control scraping time and resources.
* **Error Handling**: Incorporates `try-except` blocks to gracefully manage network issues, missing elements, and other runtime exceptions.

## Technologies Used

* **Python 3.x**
* **Selenium**: For browser automation.
* **BeautifulSoup4 (`bs4`)**: For efficient HTML parsing.
* **PyMongo**: For seamless interaction with MongoDB.
* **MongoDB Atlas (or local)**: The database solution for data storage.
* **ChromeDriver**: The WebDriver required for controlling Google Chrome.

## Setup and Installation

Follow these steps to get the scraper up and running on your local machine.

1.  **Clone the repository:**

    ```bash
    git clone [https://github.com/MusabAM/WebScrapperMongoDB.git](https://github.com/MusabAM/WebScrapperMongoDB.git)
    cd WebScrapperMongoDB
    ```
    
2.  **Create a virtual environment (recommended):**

    ```bash
    python -m venv venv
    ```

3.  **Activate the virtual environment:**

    * **On Windows:**
        ```bash
        .\venv\Scripts\activate
        ```
    * **On macOS/Linux:**
        ```bash
        source venv/bin/activate
        ```

4.  **Install Python dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

5.  **Download ChromeDriver:**
    * Ensure you have Google Chrome installed on your system.
    * Download the `chromedriver.exe` that matches your installed Chrome browser version from the official [ChromeDriver Downloads page](https://chromedriver.chromium.org/downloads).
    * **Place `chromedriver.exe` in a convenient location.** For simplicity, you can place it directly in the project's root directory. Alternatively, you can specify its full path in the `squareyards_scraper.py` file.

6.  **Set up MongoDB:**
    * You'll need a MongoDB database to store the scraped data. You can either:
        * Create a free cluster on [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
        * Set up a local MongoDB instance on your machine.
    * Obtain your **MongoDB connection URI**. This URI is crucial for the scraper to connect to your database.

## Configuration

Before running the scraper, you need to configure your database connection and scraping parameters.

1.  **Securely manage your MongoDB URI:**
    **It is highly recommended to use environment variables for your MongoDB connection URI to avoid hardcoding sensitive credentials directly in your script.**

    Create a `.env` file in the root directory of your project (the same directory as `squareyards_scraper.py`) and add your MongoDB URI:

    ```
    MONGO_URI="mongodb+srv://<username>:<password>@cluster0.xkcr7jt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    ```
    *(Replace `<username>` and `<password>` with your actual MongoDB credentials. **Do not include angle brackets.**)*

    Then, modify the `squareyards_scraper.py` file to load this variable:
    ```python
    import os
    from dotenv import load_dotenv

    # Load environment variables from .env file
    load_dotenv()

    MONGO_URI = os.getenv("MONGO_URI")
    if not MONGO_URI:
        raise ValueError("MONGO_URI environment variable not set. Please create a .env file.")

    DB_NAME = 'Svastha'
    COLLECTION_NAME = 'Squareyard Data'
    ```

2.  **Adjust other script parameters in `squareyards_scraper.py`:**

    * `DB_NAME`: The name of your database (e.g., `'Svastha'`).
    * `COLLECTION_NAME`: The name of the collection where data will be stored (e.g., `'Squareyard Data'`).
    * `RUN_DURATION_HOURS`: The maximum time the scraper will run, in hours (e.g., `1` hour).
    * `initial_search_url`: The starting URL for the SquareYards search (e.g., `"https://www.squareyards.com/ready-to-move-projects-in-bangalore"`).
    * `max_pages`: A safety limit for the number of pages the scraper will attempt to process (e.g., `50`).
    * **`service = Service("C:/Users/musab/Downloads/chromedriver-win64/chromedriver-win64/chromedriver.exe")`**: **CRITICAL!** Update the path within `Service()` to the exact location of your `chromedriver.exe`. If you placed `chromedriver.exe` in the project root, you can simplify this to `Service("./chromedriver.exe")` or `Service("chromedriver.exe")`.
    * `chrome_options.add_argument("--headless")`: Uncomment this line if you want the browser to run in the background without a visible GUI (recommended for production).

## How to Run

After completing the setup and configuration, execute the Python script from your terminal:

```bash
python squareyards_scraper.py
