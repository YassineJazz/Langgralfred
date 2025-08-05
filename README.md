# Alfred - Your Personal AI Butler

Alfred is a voice-activated personal assistant inspired by Batman's loyal butler, Alfred Pennyworth. He is designed to be a discreet, capable, and witty assistant, ready to help with a variety of tasks through natural language voice commands.

## Features

- **Voice Activation**: Alfred listens for the wake word "Alfred" before processing any commands.
- **Conversational AI**: Powered by LangChain and OpenAI's GPT-4o-mini, Alfred can understand and respond to a wide range of requests.
- **Tool Integration**: Alfred can interact with various tools and APIs to perform actions, including:
    - **Google Services**:
        - **Gmail**: Read unread emails and send new ones.
        - **Google Calendar**: List upcoming events and create new ones.
        - **Google Maps**: Get travel duration estimates.
    - **Web Search**: Use Brave Search to find information on the web.
    - **Web Navigation**: Navigate to URLs and extract text from web pages.
    - **Weather**: Get the current weather for any location.
    - **Location**: Knows your current location (currently hardcoded).
- **Real-time Speech-to-Text and Text-to-Speech**: Utilizes RealtimeSTT for transcription and ElevenLabs for realistic voice output.
- **Asynchronous Architecture**: Built with Python's `asyncio` for efficient handling of concurrent tasks.

## Getting Started

### Prerequisites

- Python 3.12 or higher
- `uv` for package management
- Google Cloud project with the Gmail and Google Calendar APIs enabled.
- Credentials for Google Cloud (`credentials.json`).
- API keys for:
    - ElevenLabs
    - Brave Search
    - Google Maps

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd LanggraphAlfred
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   uv venv
   uv pip install -r requirements.txt
   ```

3. **Set up your environment variables:**
   Create a `.env` file in the root of the project and add the following:
   ```
   ELEVENLABS_API_KEY="your_elevenlabs_api_key"
   MAPS_API_KEY="your_google_maps_api_key"
   BRAVE_API_KEY="your_brave_search_api_key"
   ```

4. **Place your Google credentials:**
   Put your `credentials.json` file in the root of the project directory.

### Running Alfred

To start the assistant, run the `main.py` script:

```bash
python main.py
```

The first time you run the application, you will be prompted to authenticate with your Google account. A `token.pickle` file will be created to store your authentication tokens for future sessions.

## How to Use

1. **Start the application.** You will see log messages indicating that the services are starting.
2. **Say the wake word "Alfred"** followed by your command. For example:
   - "Alfred, what's the weather like in London?"
   - "Alfred, do I have any unread emails?"
   - "Alfred, send an email to example@example.com with the subject 'Hello' and the body 'This is a test email.'"
   - "Alfred, what's on my calendar today?"

## Project Structure

- **`main.py`**: The entry point of the application. It initializes and runs the main components.
- **`Alfred.py`**: The core class for the assistant. It manages the state, integrates the different modules (STT, TTS, LLM), and handles the main logic.
- **`langchain_tools.py`**: Contains all the tools that Alfred can use, such as sending emails, searching the web, etc. Each tool is decorated with `@tool`.
- **`pyproject.toml`**: Defines the project dependencies.
- **`.env`**: Stores API keys and other secrets.
- **`credentials.json`**: Your Google Cloud credentials.
- **`token.pickle`**: Stores your Google authentication tokens.

## Dependencies

The main dependencies are listed in `pyproject.toml` and include:

- `langchain`, `langgraph`, `langchain-openai`
- `google-api-python-client`, `google-auth-oauthlib`
- `RealtimeSTT`, `pyaudio`, `websockets`
- `playwright`, `beautifulsoup4`
- `brave-search`, `python-weather`, `googlemaps`