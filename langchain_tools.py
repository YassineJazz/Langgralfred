import os
import pickle
import base64
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from brave import Brave
import os
from datetime import datetime, timedelta
import pytz

# --- LangChain/LangGraph Imports ---
from langchain_core.tools import tool

# --- Google Service Imports ---
import googlemaps
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Other Library Imports ---
import python_weather

# --- Environment Variable Loading ---
# Make sure your .env file has these keys
from dotenv import load_dotenv
load_dotenv()
MAPS_API_KEY = os.getenv("MAPS_API_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
brave_client = Brave(BRAVE_API_KEY)

browser_page = None
playwright_context = None
browser_instance = None
browser_page= None


# --- Google Maps Client Initialization ---
# Initialize the client once to be reused by the tool
gmaps_client = None
if MAPS_API_KEY:
    gmaps_client = googlemaps.Client(key=MAPS_API_KEY)
else:
    print("Warning: MAPS_API_KEY not found. The 'get_travel_duration' tool will not work.")

# --- Gmail API Configuration ---
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar'
]

# --- Helper Function (Not a Tool) ---
# This function handles the OAuth2 flow for Gmail.
async def google_authenticate():
    """
    Authenticates with Google APIs using OAuth2.
    Handles token creation, storage, and refresh for all required scopes.
    """
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError(
                    "Error: 'credentials.json' not found. "
                    "Please download it from your Google Cloud Console."
                )
            # Use the updated GOOGLE_SCOPES list here
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    # This function now returns the credentials, not a specific service build
    return creds

async def startup_browser():
    """Initializes the playwright browser instance and page."""
    global playwright_context, browser_instance, browser_page
    if browser_instance is None:
        print("Starting up browser...")
        playwright_context = await async_playwright().start()
        browser_instance = await playwright_context.chromium.launch()
        browser_page = await browser_instance.new_page()
        print("Browser started successfully.")

async def shutdown_browser():
    """Closes the playwright browser instance and context."""
    global playwright_context, browser_instance
    
    # The correct method is .is_connected()
    if browser_instance and browser_instance.is_connected():
        print("Shutting down browser...")
        await browser_instance.close()
        browser_instance = None

    if playwright_context:
        await playwright_context.stop()
        playwright_context = None
        print("Browser shut down successfully.")


# --- General Tools ---


@tool
def get_current_location() -> str:
    """
    Returns the user's current physical location.
    This tool should be used when the user asks 'where am I?' or for their current city.
    """
    # This is hardcoded based on the provided context.
    return "Montreal, Quebec, Canada."


# --- Weather Tool ---

@tool
async def get_weather(location: str) -> str:
    """
    Gets the current weather conditions (temperature, precipitation, description)
    for a specified city and state/country (e.g., 'Vinings, GA', 'London, UK').
    """
    async with python_weather.Client(unit=python_weather.IMPERIAL) as client:
        try:
            weather = await client.get(location)
            response = (
                f"The current weather in {location} is {weather.temperature}°F "
                f"with {weather.description}. "
                f"Precipitation is {weather.precipitation}."
            )
            print(f"Weather tool generated response: {response}")
            return response
        except Exception as e:
            print(f"Error fetching weather for {location}: {e}")
            return f"Sorry, I could not fetch the weather for {location}."


# --- Travel Tool ---

@tool
def get_travel_duration(origin: str, destination: str, mode: str = "driving") -> str:
    """
    Calculates the estimated travel duration between a specified origin and destination
    using Google Maps. Considers current traffic for driving mode.
    The 'mode' can be 'driving', 'walking', 'bicycling', or 'transit'.
    """
    if not gmaps_client:
        return "Error: The Google Maps client is not configured. Please check the API key."
    try:
        now = datetime.now()
        print(f"Requesting directions: From='{origin}', To='{destination}', Mode='{mode}'")
        directions_result = gmaps_client.directions(origin, destination, mode=mode, departure_time=now)

        if not directions_result:
            return f"Could not find a route from {origin} to {destination} via {mode}."

        leg = directions_result[0]['legs'][0]
        result = f"Estimated travel duration from {origin} to {destination} by {mode}"

        if mode == "driving" and 'duration_in_traffic' in leg:
            duration_text = leg['duration_in_traffic']['text']
            result += f" (with current traffic): {duration_text}."
        elif 'duration' in leg:
            duration_text = leg['duration']['text']
            result += f": {duration_text}."
        else:
            result = "Duration information not found in the response."

        print(f"Travel duration tool generated response: {result}")
        return result
    except googlemaps.exceptions.ApiError as api_err:
        print(f"Google Maps API Error: {api_err}")
        return f"Error contacting Google Maps: {api_err}"
    except Exception as e:
        print(f"An unexpected error occurred during travel duration lookup: {e}")
        return f"An unexpected error occurred: {e}"


# --- Gmail Tools ---

@tool
async def list_unread_messages(max_results: int = 5) -> list[str]:
    """
    Lists the subjects of up to `max_results` unread emails from the user's Gmail account.
    This tool is useful for checking for new or important emails.
    """
    try:
        creds = await google_authenticate()
        service = build('gmail', 'v1', credentials=creds)
        # Call the Gmail API
        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], q="is:unread", maxResults=max_results).execute()
        messages = results.get('messages', [])

        if not messages:
            return ["No unread messages found."]

        response_lines = []
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            headers = msg['payload']['headers']
            subject = next(header['value'] for header in headers if header['name'] == 'Subject')
            sender = next(header['value'] for header in headers if header['name'] == 'From')
            response_lines.append(f"From: {sender} - Subject: {subject}")

        return response_lines
    except HttpError as error:
        return [f"Gmail API error: {error.reason}. You might need to re-authenticate."]
    except Exception as e:
        return [f"An unexpected error occurred: {e}"]


@tool
async def send_email(to: str, subject: str, body: str) -> str:
    """
    Sends an email from the user's Gmail account.
    Requires the recipient's email address, a subject line, and the body of the email.
    """
    try:
        creds = await google_authenticate()
        service = build('gmail', 'v1', credentials=creds)
        message = {
            'raw': base64.urlsafe_b64encode(
                f"To: {to}\r\n"
                f"Subject: {subject}\r\n\r\n"
                f"{body}".encode('utf-8')
            ).decode('utf-8')
        }
        sent_message = service.users().messages().send(userId='me', body=message).execute()
        return f"Email sent successfully to {to}. Message ID: {sent_message['id']}"
    except HttpError as error:
        return f"Failed to send email due to a Gmail API error: {error.reason}."
    except Exception as e:
        return f"Failed to send email: {e}"
    
@tool
def brave_search(query: str) -> str:
    """
    Performs a web search using the Brave Search API to get a list of results.
    Use this to find information, articles, or websites on a given topic.
    """
    if not brave_client:
        return "Error: Brave Search client is not configured."
    print(f"Searching the web for: '{query}'")
    try:
        search_results = brave_client.search(q=query)
        # Format the results for the LLM
        formatted_results = []
        for i, result in enumerate(search_results.web.results[:5]): # Return top 5 results
            formatted_results.append(
                f"{i+1}. {result.title}\n"
                f"   URL: {result.url}\n"
                f"   Description: {result.description}\n"
            )
        return "\n".join(formatted_results) if formatted_results else "No search results found."
    except Exception as e:
        return f"Error performing search: {e}"



@tool
async def navigate_to_url(url: str) -> str:
    """
    Navigates the shared browser to a specified URL.
    Use this after finding a URL with the search tool.
    """
    if browser_page is None:
        return "Error: The browser is not running. Please start it first."
    print(f"Navigating to URL: {url}")
    try:
        await browser_page.goto(url, wait_until="domcontentloaded")
        return f"Successfully navigated to {url}. The page title is '{await browser_page.title()}'."
    except Exception as e:
        return f"Error navigating to {url}: {e}"


@tool
async def extract_page_text() -> str:
    """
    Extracts and returns the clean, visible text content from the current browser page.
    Use this after navigating to a page to read its content.
    """
    if browser_page is None:
        return "Error: The browser is not running."
    print("Extracting text from current page...")
    try:
        html_content = await browser_page.content()
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = "\n".join(chunk for chunk in chunks if chunk)
        
        # Truncate to avoid excessively long content
        return clean_text[:8000]
    except Exception as e:
        return f"Error extracting text from page: {e}"
@tool
async def list_calendar_events(max_results: int = 10) -> str:
    """
    Lists the next upcoming events from the user's primary Google Calendar.
    `max_results` specifies the maximum number of events to return.
    """
    try:
        creds = await google_authenticate()
        service = build('calendar', 'v3', credentials=creds)
        
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print(f"Getting upcoming {max_results} events from Google Calendar...")
        
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return "No upcoming events found."

        event_lines = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            event_lines.append(f"- {event['summary']} (Starts: {start})")
            
        return "\n".join(event_lines)
    except Exception as e:
        return f"An error occurred with the Calendar tool: {e}"


@tool
async def create_calendar_event(summary: str, start_time: str, end_time: str, location: str = None, description: str = None) -> str:
    """
    Creates a new event on the user's primary Google Calendar.
    The start_time and end_time must be in ISO 8601 format (e.g., '2025-07-15T10:00:00-04:00').
    The timezone offset (e.g., -04:00) is important.
    """
    try:
        creds = await google_authenticate()
        service = build('calendar', 'v3', credentials=creds)

        event = {
            'summary': summary,
            'location': location,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'Morocco/Casablanca', # You can make this an argument later if needed
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Morocco/Casablanca',
            },
        }

        print(f"Creating calendar event: {summary}")
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        
        return f"Event created successfully: {created_event.get('htmlLink')}"
    except Exception as e:
        return f"An error occurred creating the calendar event: {e}"
