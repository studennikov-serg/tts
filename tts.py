import json
import os
import sys
import time
import requests
import re # Import regex module for sentence splitting
import subprocess # For calling external commands like ffmpeg
import argparse # For command-line argument parsing

# Import for non-blocking single character input
try:
    import msvcrt # Windows-specific
except ImportError:
    import termios # Unix-specific
    import tty # Unix-specific

from google.oauth2 import service_account
from google.auth.transport.requests import Request

# --- Configuration and File Paths ---
CREDENTIALS_FILE = "credentials-tts.json"
SETTINGS_FILE = "settings.json"
TEXTS_DIR = "texts"
AUDIO_DIR = os.path.join(TEXTS_DIR, "audio")
DATA_FILE = os.path.join(TEXTS_DIR, "data.txt")

# --- Google Cloud TTS Voice Settings (Easily Configurable) ---
TTS_LANGUAGE_CODE = "en-GB"
TTS_VOICE_NAME = "en-GB-Chirp3-HD-Sadaltager"
TTS_SPEAKING_RATE = 0.9
TTS_AUDIO_ENCODING = "LINEAR16" # WAV format (e.g., LINEAR16, MP3, OGG_OPUS)

# --- Global Variables ---
settings = {}
credentials = None
project_id = None
access_token = None
_ffmpeg_error_printed = False # Flag to suppress repeated ffmpeg errors

# --- Helper Functions for User Interaction ---

def _getch():
    """Reads a single character from stdin without echoing it or requiring Enter."""
    if 'msvcrt' in sys.modules:
        # Windows
        return msvcrt.getch().decode('utf-8')
    else:
        # Unix/Linux/macOS
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

def clear_console():
    """Clears the terminal console."""
    os.system('cls' if os.name == 'nt' else 'clear')

def exit_script(save_position=False, current_index=0):
    """Exits the script gracefully, optionally saving the current position."""
    if save_position:
        settings["last_processed_sentence"] = current_index
        save_settings()
    sys.exit(0)

# --- Core Logic Functions ---

def load_settings():
    """Loads settings from settings.json or initializes default settings."""
    global settings
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        # Ensure the correct key is used, migrate if old key exists
        if "last_processed_paragraph" in settings and "last_processed_sentence" not in settings:
            settings["last_processed_sentence"] = settings.pop("last_processed_paragraph")
            save_settings() # Save migrated settings
    except FileNotFoundError:
        settings = {"last_processed_sentence": 0}
        save_settings()
    except json.JSONDecodeError:
        settings = {"last_processed_sentence": 0}
        save_settings()
    except IOError as e:
        print(f"Error loading settings from {SETTINGS_FILE}: {e}")
        settings = {"last_processed_sentence": 0}
        save_settings() # Attempt to create default settings if loading fails

def save_settings():
    """Saves current settings to settings.json."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except IOError as e:
        print(f"Error saving settings to {SETTINGS_FILE}: {e}")

def get_credentials():
    """
    Attempts to load Google Cloud TTS credentials from credentials-tts.json.
    If the file doesn't exist, it provides instructions on how to get them.
    Returns True on success, False on failure.
    """
    global credentials, project_id, access_token

    if os.path.exists(CREDENTIALS_FILE):
        try:
            credentials = service_account.Credentials.from_service_account_file(
                CREDENTIALS_FILE,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            credentials.refresh(Request()) # Refresh token if necessary
            access_token = credentials.token
            project_id = credentials.project_id
            if access_token and project_id:
                return True
            else:
                return False
        except Exception as e:
            print(f"Error loading credentials from {CREDENTIALS_FILE}: {e}")
            print("Please ensure the JSON file is valid and contains a service account key.")
            return False
    else:
        print(f"'{CREDENTIALS_FILE}' not found.")
        print("To use Google Cloud Text-to-Speech API, you need a service account key file.")
        print("Please follow the setup instructions in the README.md section within this script's comments.")
        print(f"Place '{CREDENTIALS_FILE}' in the current directory and restart the script.")
        return False


def read_sentences():
    """Reads data.txt and splits it into sentences."""
    if not os.path.exists(DATA_FILE):
        print(f"Error: '{DATA_FILE}' not found.")
        print(f"Please create a '{TEXTS_DIR}' folder and put your text in '{DATA_FILE}'.")
        exit_script()

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex to split sentences, keeping the delimiter.
        # This one handles common cases and tries to avoid splitting on abbreviations.
        # It looks for . ! ? followed by whitespace or end of string,
        # but not preceded by a capital letter (for abbreviations like Mr. or U.S.).
        sentences = re.findall(r'(?<![A-Z]\.)[^.!?]+(?:[.!?](?=\s|$))?', content)
        # Further clean up and strip whitespace
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            print(f"Warning: '{DATA_FILE}' is empty or contains no discernible sentences.")
            exit_script()
        return sentences
    except Exception as e:
        print(f"Error reading '{DATA_FILE}': {e}")
        exit_script()

def synthesize_text(text, sentence_number):
    """
    Sends a sentence to Google Cloud TTS API and returns the audio content.
    Args:
        text (str): The text to synthesize.
        sentence_number (int): The current sentence number for logging.
    Returns:
        bytes: The audio content in WAV format, or None if an error occurs.
    """
    global access_token, project_id # Allow modification if token is refreshed

    if not access_token or not project_id:
        # Try to refresh credentials if they are missing during an active session
        if get_credentials():
            pass # Credentials reloaded successfully
        else:
            print("Failed to re-obtain valid credentials. Cannot synthesize.")
            return None

    api_url = f"https://texttospeech.googleapis.com/v1/text:synthesize"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id,
        "Authorization": f"Bearer {access_token}"
    }

    payload = {
        "input": {
            "text": text
        },
        "voice": {
            "languageCode": TTS_LANGUAGE_CODE,
            "name": TTS_VOICE_NAME,
            "voiceClone": {} # Empty voiceClone as per template
        },
        "audioConfig": {
            "audioEncoding": TTS_AUDIO_ENCODING,
            "speakingRate": TTS_SPEAKING_RATE
        }
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        audio_content = response.json().get("audioContent")
        if audio_content:
            import base64
            return base64.b64decode(audio_content)
        else:
            print(f"Synthesis Error: No audio content received for sentence {sentence_number}.")
            return None
    except requests.exceptions.HTTPError as http_err:
        print(f"Synthesis HTTP error: {http_err.response.status_code}") # Short info
        if http_err.response.status_code == 403:
            print("Synthesis Error: Permission denied. Check TTS role.")
        elif http_err.response.status_code == 401:
            print("Synthesis Error: Unauthorized. Attempting token refresh...")
            credentials.refresh(Request())
            access_token = credentials.token
            print("Token refreshed. Try recording again.")
        return None
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Synthesis Error: Connection error: {conn_err}")
        return None
    except requests.exceptions.Timeout as timeout_err:
        print(f"Synthesis Error: Timeout: {timeout_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"Synthesis Error: Unexpected request error: {req_err}")
        return None
    except json.JSONDecodeError:
        print(f"Synthesis Error: JSON decode error in response.")
        return None
    except Exception as e:
        print(f"Synthesis Error: Unexpected error: {e}")
        return None

def save_audio(audio_content, sentence_index):
    """
    Saves the audio content to a WAV file.
    Args:
        audio_content (bytes): The binary audio data.
        sentence_index (int): The 0-based index of the sentence.
    Returns:
        str: The path to the saved file, or None if saving fails.
    """
    os.makedirs(AUDIO_DIR, exist_ok=True)
    filename = f"{sentence_index + 1:03d}.wav" # 0-padded to 3 digits, 1-based number
    filepath = os.path.join(AUDIO_DIR, filename)
    try:
        with open(filepath, 'wb') as f:
            f.write(audio_content)
        return filepath
    except IOError as e:
        print(f"Error saving audio to {filepath}: {e}")
        return None

def play_audio(filepath):
    """
    Plays an audio file using ffplay (part of FFmpeg).
    Suppresses repeated errors.
    """
    global _ffmpeg_error_printed
    player_command = ["ffplay"] # Default for Linux/macOS
    if sys.platform == "win32":
        player_command = ["ffplay.exe"] # For Windows

    # Suppress stdout and stderr for a cleaner console
    try:
        subprocess.run(player_command + ["-nodisp", "-autoexit", filepath],
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        if not _ffmpeg_error_printed:
            print("\nError: 'ffplay' command not found.")
            print("Please ensure FFmpeg is installed and 'ffplay' is in your system's PATH.")
            _ffmpeg_error_printed = True
    except subprocess.CalledProcessError as e:
        if not _ffmpeg_error_printed:
            print(f"\nError playing audio with ffplay: {e}")
            _ffmpeg_error_printed = True
    except Exception as e:
        if not _ffmpeg_error_printed:
            print(f"\nAn unexpected error occurred during audio playback: {e}")
            _ffmpeg_error_printed = True


def display_sentence(sentences, current_index, recorded=False):
    """Clears console and displays the current sentence (without sentence number)."""
    clear_console()
    if recorded:
        print("*", end=" ") # Print asterisk for recorded sentences
    print(sentences[current_index])


def print_readme():
    """Prints the content of the README.md from the script's docstring."""
    readme_content = """
# Google Cloud TTS Sentence Processor (Interactive CLI)

This Python script helps you convert text sentences from a file into audio WAV files using Google Cloud Text-to-Speech API. It provides an interactive command-line interface for navigating, processing, and re-recording sentences.

## Features:
- Reads text from `texts/data.txt` and splits it into individual sentences.
- Uses Google Cloud Text-to-Speech API for synthesis.
- Saves generated audio files as `001.wav`, `002.wav`, etc., in `texts/audio/`.
- Remembers the last processed sentence's position using `settings.json` when quitting with 'q'.
- Interactive, non-blocking key presses for navigation and actions.
- Displays the full current sentence on the console, clearing previous output.
- Marks recorded sentences with an asterisk (`*`).
- Plays recorded audio using `ffplay` (part of FFmpeg).
- TTS voice settings are easily configurable at the top of the script.

## Interactive Key Bindings:
-   **`J` (or `j`):** Move to the previous sentence (if available).
-   **`L` (or `l`):** Move to the next sentence (if available). Saves current position when moving to the next.
-   **Spacebar (` `):** Record (synthesize) the current sentence. If already recorded, it will re-record and play the audio.
-   **`R` (or `r`):** Reload `data.txt`. The cursor (current sentence position) will remain at its current index if possible, otherwise it will adjust to the new range.
-   **`Q` (or `q`):** Quit the script and save the last processed sentence's position.
-   **`Ctrl+C`:** Quit the script *without* saving the last processed sentence's position.

## Setup:

1.  **Python Environment:**
    Make sure you have Python 3 installed.
    Install the necessary libraries:
    ```bash
    pip install google-auth google-auth-oauthlib requests
    ```
    Depending on your OS, you might need to ensure `msvcrt` (Windows) / `termios`, `tty` (Unix-like) are available for non-blocking input. These are standard library modules.

2.  **FFmpeg Installation:**
    Ensure FFmpeg is installed on your system and `ffplay` (or `ffplay.exe` on Windows) is accessible via your system's PATH.
    -   **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install ffmpeg`
    -   **Linux (Fedora):** `sudo dnf install ffmpeg`
    -   **Windows:** Download a pre-built binary from the official FFmpeg website and add its `bin` directory to your System PATH.

3.  **Google Cloud Project & Credentials:**
    You need a Google Cloud Project with the Text-to-Speech API enabled and a Service Account key file.
    Follow these steps to obtain your `credentials-tts.json` file:

    a.  **Go to Google Cloud Console:**
        Open your web browser and go to `https://console.cloud.google.com/`.

    b.  **Select or Create a Project:**
        Choose an existing project or create a new one.

    c.  **Enable Text-to-Speech API:**
        Navigate to `APIs & Services` > `Enabled APIs & Services`.
        Click `+ ENABLE APIS AND SERVICES`.
        Search for "Cloud Text-to-Speech API" and enable it.

    d.  **Create a Service Account:**
        Navigate to `IAM & Admin` > `Service Accounts`.
        Click `+ CREATE SERVICE ACCOUNT`.
        Give it a name (e.g., `tts-service-account`).
        Click `DONE`.

    e.  **Grant Permissions:**
        In the list of service accounts, find the one you just created and click on its email address.
        Go to the `Permissions` tab.
        Click `GRANT ACCESS`.
        In the `New principals` field, add the service account you just created.
        In the `Select a role` dropdown, search for and select `Cloud Text-to-Speech User`.
        Click `SAVE`.
        **Important:** If you encounter `INVALID_ARGUMENT` errors during role assignment via CLI, you might need to grant a broader role like `Editor` temporarily, and then narrow it down manually in the console after successful API usage.

    f.  **Create a JSON Key:**
        Go back to the `Service Accounts` page (`IAM & Admin` > `Service Accounts`).
        Click on the email address of your service account.
        Go to the `Keys` tab.
        Click `ADD KEY` > `Create new key`.
        Select `JSON` as the key type and click `CREATE`.
        A JSON file will be downloaded to your computer.

    g.  **Rename and Place the Key File:**
        Rename the downloaded JSON file to `credentials-tts.json`.
        Place this `credentials-tts.json` file in the same directory as your Python script.

4.  **Text Data:**
    Create a folder named `texts` in the same directory as your script.
    Inside the `texts` folder, create a file named `data.txt`.
    Paste the text you want to convert into `data.txt`. The script will now split the content into individual sentences.

5.  **Audio Output Folder:**
    The script will automatically create a folder named `audio` inside the `texts` folder (`texts/audio/`) to store the generated WAV files.

## Usage:

1.  **Run the script:**
    ```bash
    python your_script_name.py
    ```
    (Replace `your_script_name.py` with the actual name of your Python file).

2.  **Interact using keys:**
    Use `j` and `l` to navigate, `Spacebar` to record/play, `R` to reload text, and `Q` to quit.

## Important Notes:

-   **Sentence Definition:** The script attempts to split text into sentences based on common punctuation (`.`, `!`, `?`), trying to handle some abbreviations. Complex sentence structures or unusual text might not be perfectly split. Review `data.txt` content if sentences are not as expected.
-   **Voice Configuration:** The default voice settings are at the top of the script (`TTS_LANGUAGE_CODE`, `TTS_VOICE_NAME`, `TTS_SPEAKING_RATE`, `TTS_AUDIO_ENCODING`).
-   **Error Handling:** The script includes basic error handling for file operations and API calls. API token refresh attempts are made automatically if an unauthorized error occurs. FFmpeg errors are suppressed after the first occurrence in a session.
-   **Console Environment:** Ensure your terminal supports ANSI escape codes for clearing the screen (most modern terminals do).
"""
    print(readme_content)


def main():
    """Main function to run the TTS processing script with interactive CLI."""
    global _ffmpeg_error_printed # Declare global for assignment within main

    # 1. Handle command-line arguments
    parser = argparse.ArgumentParser(add_help=False) # add_help=False to handle it manually
    parser.add_argument('--help', action='store_true', help='Show this help message and exit.')
    args = parser.parse_args()

    if args.help:
        clear_console() # Clear before printing full README
        print_readme()
        sys.exit(0)

    # Initial setup messages - these should NOT be cleared immediately
    print("--- Google Cloud TTS Sentence Processor ---")

    # Load settings on start
    load_settings()

    # Get Google Cloud TTS credentials (will prompt for setup if missing, then exit)
    if not get_credentials():
        sys.exit(0) # Exit if credentials are not available

    sentences = []
    current_sentence_index = settings.get("last_processed_sentence", 0)
    
    # Initial load of sentences
    try:
        sentences = read_sentences()
        # Adjust index if it's out of bounds after initial load (e.g., data.txt shrank)
        if current_sentence_index >= len(sentences):
            current_sentence_index = len(sentences) - 1 if len(sentences) > 0 else 0
            settings["last_processed_sentence"] = current_sentence_index
            save_settings() # Save adjusted index
    except SystemExit: # read_sentences might call exit_script
        sys.exit(0) # Propagate the exit


    # Print initial sentence number and keys once at the start (before the first clear_console)
    total_sentences = len(sentences)
    if total_sentences > 0:
        print(f"Starting at Sentence {current_sentence_index + 1} / {total_sentences}")
    print("------------------------------------------------------------------")
    print("Keys: J prev | L next | Space record/play | R reload | Q quit (Ctrl+C to exit without saving)")
    print("------------------------------------------------------------------")
    time.sleep(1) # Give user a moment to read initial message

    # --- Clear the console once before starting the interactive part of the loop ---
    clear_console()

    # Main interactive loop
    while True:
        # Re-calculate sentence_audio_exists for the *current* current_sentence_index
        # This ensures its state is always accurate before display.
        sentence_audio_exists = os.path.exists(os.path.join(AUDIO_DIR, f"{current_sentence_index + 1:03d}.wav"))

        try:
            if not sentences:
                clear_console()
                print("No sentences found in data.txt. Please add text and press 'R' to reload.")
                key = _getch().lower() # Read and convert to lowercase for case-insensitivity
                if key == 'q':
                    exit_script(save_position=True, current_index=current_sentence_index) # Save on 'q'
                elif key == 'r':
                    _ffmpeg_error_printed = False # Reset ffmpeg error flag on reload
                    sentences = read_sentences()
                    # Preserve cursor position logic already handled after read_sentences
                    if current_sentence_index >= len(sentences):
                        current_sentence_index = len(sentences) - 1 if len(sentences) > 0 else 0
                    # Update audio existence status for the new current sentence after reload
                    sentence_audio_exists = os.path.exists(os.path.join(AUDIO_DIR, f"{current_sentence_index + 1:03d}.wav"))
                    
                    # After reload, print sentence number to indicate new state (as requested)
                    if len(sentences) > 0:
                        clear_console() # Clear to show the new count
                        print(f"Sentence {current_sentence_index + 1} / {len(sentences)}")
                    
                continue # Restart loop to display
            
            # The display_sentence function itself handles clearing the console
            # and printing the sentence and asterisk.
            display_sentence(sentences, current_sentence_index, sentence_audio_exists)

            key = _getch().lower() # Read single key press and convert to lowercase

            if key == 'l': # Next sentence
                if current_sentence_index < len(sentences) - 1:
                    current_sentence_index += 1
                    # Save position only when moving forward to the next sentence
                    settings["last_processed_sentence"] = current_sentence_index
                    save_settings()
                else:
                    pass # Do nothing if at the end
            elif key == 'j': # Previous sentence
                if current_sentence_index > 0:
                    current_sentence_index -= 1
            elif key == ' ': # Spacebar: record/re-record and play
                audio_data = synthesize_text(sentences[current_sentence_index], current_sentence_index + 1)
                if audio_data:
                    filepath = save_audio(audio_data, current_sentence_index)
                    if filepath:
                        # sentence_audio_exists will be re-calculated at start of next loop iteration
                        play_audio(filepath) # Play the newly recorded audio
            elif key == 'r': # Reload text file
                _ffmpeg_error_printed = False # Reset ffmpeg error flag on reload
                old_index = current_sentence_index
                try:
                    sentences = read_sentences()
                    new_total_sentences = len(sentences)
                    # Keep cursor position, but adjust if new total is smaller or 0
                    if old_index < new_total_sentences:
                        current_sentence_index = old_index
                    elif new_total_sentences > 0:
                        current_sentence_index = new_total_sentences - 1
                    else:
                        current_sentence_index = 0 # No sentences after reload
                    
                    # After reload, print sentence number to indicate new state (as requested)
                    if len(sentences) > 0:
                        clear_console() # Clear to show the new count
                        print(f"Sentence {current_sentence_index + 1} / {len(sentences)}")
                    
                except SystemExit:
                    sys.exit(0) # Propagate exit if read_sentences fails critically
            elif key == 'q': # Quit
                exit_script(save_position=True, current_index=current_sentence_index) # Save on 'q'

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully without saving position as requested
            exit_script(save_position=False)
        except Exception as e:
            clear_console() # Clear to show error clearly
            print(f"An unexpected error occurred in the main loop: {e}")
            print("Press 'q' to quit or any other key to continue (may lead to further errors).")
            key = _getch().lower()
            if key == 'q':
                exit_script(save_position=True, current_index=current_sentence_index) # Save on 'q'


# --- README.md (Multi-line comment) ---
"""
# Google Cloud TTS Sentence Processor (Interactive CLI)

This Python script helps you convert text sentences from a file into audio WAV files using Google Cloud Text-to-Speech API. It provides an interactive command-line interface for navigating, processing, and re-recording sentences.

## Features:
- Reads text from `texts/data.txt` and splits it into individual sentences.
- Uses Google Cloud Text-to-Speech API for synthesis.
- Saves generated audio files as `001.wav`, `002.wav`, etc., in `texts/audio/`.
- Remembers the last processed sentence's position using `settings.json` when quitting with 'q'.
- Interactive, non-blocking key presses for navigation and actions.
- Displays the full current sentence on the console, clearing previous output.
- Marks recorded sentences with an asterisk (`*`).
- Plays recorded audio using `ffplay` (part of FFmpeg).
- TTS voice settings are easily configurable at the top of the script.

## Interactive Key Bindings:
-   **`J` (or `j`):** Move to the previous sentence (if available).
-   **`L` (or `l`):** Move to the next sentence (if available). Saves current position when moving to the next.
-   **Spacebar (` `):** Record (synthesize) the current sentence. If already recorded, it will re-record and play the audio.
-   **`R` (or `r`):** Reload `data.txt`. The cursor (current sentence position) will remain at its current index if possible, otherwise it will adjust to the new range.
-   **`Q` (or `q`):** Quit the script and save the last processed sentence's position.
-   **`Ctrl+C`:** Quit the script *without* saving the last processed sentence's position.

## Setup:

1.  **Python Environment:**
    Make sure you have Python 3 installed.
    Install the necessary libraries:
    ```bash
    pip install google-auth google-auth-oauthlib requests
    ```
    Depending on your OS, you might need to ensure `msvcrt` (Windows) / `termios`, `tty` (Unix-like) are available for non-blocking input. These are standard library modules.

2.  **FFmpeg Installation:**
    Ensure FFmpeg is installed on your system and `ffplay` (or `ffplay.exe` on Windows) is accessible via your system's PATH.
    -   **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install ffmpeg`
    -   **Linux (Fedora):** `sudo dnf install ffmpeg`
    -   **Windows:** Download a pre-built binary from the official FFmpeg website and add its `bin` directory to your System PATH.

3.  **Google Cloud Project & Credentials:**
    You need a Google Cloud Project with the Text-to-Speech API enabled and a Service Account key file.
    Follow these steps to obtain your `credentials-tts.json` file:

    a.  **Go to Google Cloud Console:**
        Open your web browser and go to `https://console.cloud.google.com/`.

    b.  **Select or Create a Project:**
        Choose an existing project or create a new one.

    c.  **Enable Text-to-Speech API:**
        Navigate to `APIs & Services` > `Enabled APIs & Services`.
        Click `+ ENABLE APIS AND SERVICES`.
        Search for "Cloud Text-to-Speech API" and enable it.

    d.  **Create a Service Account:**
        Navigate to `IAM & Admin` > `Service Accounts`.
        Click `+ CREATE SERVICE ACCOUNT`.
        Give it a name (e.g., `tts-service-account`).
        Click `DONE`.

    e.  **Grant Permissions:**
        In the list of service accounts, find the one you just created and click on its email address.
        Go to the `Permissions` tab.
        Click `GRANT ACCESS`.
        In the `New principals` field, add the service account you just created.
        In the `Select a role` dropdown, search for and select `Cloud Text-to-Speech User`.
        Click `SAVE`.
        **Important:** If you encounter `INVALID_ARGUMENT` errors during role assignment via CLI, you might need to grant a broader role like `Editor` temporarily, and then narrow it down manually in the console after successful API usage.

    f.  **Create a JSON Key:**
        Go back to the `Service Accounts` page (`IAM & Admin` > `Service Accounts`).
        Click on the email address of your service account.
        Go to the `Keys` tab.
        Click `ADD KEY` > `Create new key`.
        Select `JSON` as the key type and click `CREATE`.
        A JSON file will be downloaded to your computer.

    g.  **Rename and Place the Key File:**
        Rename the downloaded JSON file to `credentials-tts.json`.
        Place this `credentials-tts.json` file in the same directory as your Python script.

4.  **Text Data:**
    Create a folder named `texts` in the same directory as your script.
    Inside the `texts` folder, create a file named `data.txt`.
    Paste the text you want to convert into `data.txt`. The script will now split the content into individual sentences.

5.  **Audio Output Folder:**
    The script will automatically create a folder named `audio` inside the `texts` folder (`texts/audio/`) to store the generated WAV files.

## Usage:

1.  **Run the script:**
    ```bash
    python your_script_name.py
    ```
    (Replace `your_script_name.py` with the actual name of your Python file).

2.  **Interact using keys:**
    Use `j` and `l` to navigate, `Spacebar` to record/play, `R` to reload text, and `Q` to quit.

## Important Notes:

-   **Sentence Definition:** The script attempts to split text into sentences based on common punctuation (`.`, `!`, `?`), trying to handle some abbreviations. Complex sentence structures or unusual text might not be perfectly split. Review `data.txt` content if sentences are not as expected.
-   **Voice Configuration:** The default voice settings are at the top of the script (`TTS_LANGUAGE_CODE`, `TTS_VOICE_NAME`, `TTS_SPEAKING_RATE`, `TTS_AUDIO_ENCODING`).
-   **Error Handling:** The script includes basic error handling for file operations and API calls. API token refresh attempts are made automatically if an unauthorized error occurs. FFmpeg errors are suppressed after the first occurrence in a session.
-   **Console Environment:** Ensure your terminal supports ANSI escape codes for clearing the screen (most modern terminals do).
"""

if __name__ == "__main__":
    main()
