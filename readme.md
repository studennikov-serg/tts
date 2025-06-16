# Google Cloud TTS Sentence Processor (Interactive CLI)

What problem does this script solve?
Google TTS, its modern voices, insert idiotic additions into your text. Maybe someone thinks that this is expressive and cool. But in reality, it makes the voices useless.
There is one trick: if you split the text into sentences and transform them separately, there are no idiotic inserts.

Also see the init-tts.sh script.
This is the initialization of the project for using TTS with one command instead of fiddling with the web console. It also bypasses one problem that is difficult to solve from the GCloud CLI. See the description below.

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
    python tts.py
    ```

2.  **Interact using keys:**
    Use `j` and `l` to navigate, `Spacebar` to record/play, `R` to reload text, and `Q` to quit.

## Important Notes:

-   **Sentence Definition:** The script attempts to split text into sentences based on common punctuation (`.`, `!`, `?`), trying to handle some abbreviations. Complex sentence structures or unusual text might not be perfectly split. Review `data.txt` content if sentences are not as expected.
-   **Voice Configuration:** The default voice settings are at the top of the script (`TTS_LANGUAGE_CODE`, `TTS_VOICE_NAME`, `TTS_SPEAKING_RATE`, `TTS_AUDIO_ENCODING`).
-   **Error Handling:** The script includes basic error handling for file operations and API calls. API token refresh attempts are made automatically if an unauthorized error occurs. FFmpeg errors are suppressed after the first occurrence in a session.
-   **Console Environment:** Ensure your terminal supports ANSI escape codes for clearing the screen (most modern terminals do).

