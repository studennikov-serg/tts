#!/bin/bash

# This script automates the setup of Google Cloud Text-to-Speech API credentials.
# It aims to bypass the "INVALID_ARGUMENT: Role roles/cloudtts.user is not supported for this resource" error
# by granting a broader 'roles/editor' role as a troubleshooting step.
#
# It will:
# 1. Prompt for your Google Cloud Project ID.
# 2. Enable the Text-to-Speech API for that project.
# 3. Create a dedicated service account for TTS.
# 4. Grant the service account the 'Editor' role (roles/editor) at the project level.
#    (WARNING: This is a broad role and should be narrowed down for production use.)
# 5. VERIFY the role binding immediately after attempting it.
# 6. Generate and save a JSON key file (credentials-tts.json) for the service account.
# 7. Provide troubleshooting steps if API usage still fails.

# --- Prerequisites ---
# Ensure you have the Google Cloud SDK (gcloud CLI) installed and authenticated.
# You can authenticate by running: gcloud auth login
# The user running this script must have sufficient permissions (e.g., Project Owner or Project IAM Admin)
# to enable APIs, create service accounts, and manage IAM policies on the specified project.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Google Cloud Text-to-Speech API Credentials Setup (Troubleshooting Mode) ---"
echo "WARNING: This script will attempt to grant 'roles/editor' to the service account."
echo "This is a broad permission and is intended for troubleshooting. For production, you should use more specific roles."
echo ""
echo "This script requires the 'gcloud' CLI to be installed and authenticated."
echo "If you haven't already, please run 'gcloud auth login' in your terminal."

# Check if gcloud command exists
if ! command -v gcloud &> /dev/null
then
    echo "Error: gcloud CLI is not installed."
    echo "Please install Google Cloud SDK from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Suggest updating gcloud components
echo ""
echo "It's highly recommended to ensure your gcloud components are up to date."
read -p "Would you like to run 'gcloud components update' now? (y/n): " update_choice
if [[ "$update_choice" == "y" || "$update_choice" == "Y" ]]; then
    echo "Running gcloud components update..."
    gcloud components update --quiet || { echo "Warning: gcloud components update failed. This might indicate a problem with your gcloud installation."; }
    echo "gcloud components update completed."
else
    echo "Skipping gcloud components update."
fi
echo ""

# Display gcloud version for diagnostic purposes
echo "Your gcloud version:"
gcloud version
echo ""

# --- 1. Get Google Cloud Project ID ---
read -p "Enter your Google Cloud Project ID (e.g., my-gcp-project-123): " GCP_PROJECT_ID

if [ -z "$GCP_PROJECT_ID" ]; then
    echo "Project ID cannot be empty. Exiting."
    exit 1
fi

# Set the project for gcloud commands
echo "Setting gcloud project to: $GCP_PROJECT_ID"
gcloud config set project "$GCP_PROJECT_ID" || { echo "Error: Failed to set gcloud project. Please ensure the Project ID is correct and you have access to it."; exit 1; }

# --- 2. Enable the Text-to-Speech API ---
echo "Enabling the Cloud Text-to-Speech API (texttospeech.googleapis.com)..."
gcloud services enable texttospeech.googleapis.com || { echo "Error: Failed to enable Text-to-Speech API. Check your project ID and that you have 'Service Usage Admin' or 'Owner' permissions."; exit 1; }

# Increased delay to allow API enablement to propagate
echo "API enablement initiated. Waiting 10 seconds for propagation to minimize permission issues..."
sleep 10

echo "Cloud Text-to-Speech API enabled successfully."

# --- 3. Create a Service Account ---
SERVICE_ACCOUNT_NAME="tts-service-account-$(date +%s)" # Unique name with timestamp
SERVICE_ACCOUNT_ID="${SERVICE_ACCOUNT_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
SERVICE_ACCOUNT_DISPLAY_NAME="Text-to-Speech Automation Service Account"

echo "Creating service account: ${SERVICE_ACCOUNT_DISPLAY_NAME} (${SERVICE_ACCOUNT_ID})..."
if ! gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --display-name="$SERVICE_ACCOUNT_DISPLAY_NAME" \
    --project="$GCP_PROJECT_ID"; then
    echo "Error: Failed to create service account. This could be due to insufficient permissions (e.g., 'Service Account Admin' role needed) or an invalid project ID."
    exit 1
fi
echo "Service account created successfully."

# --- 4. Grant the Service Account the 'Editor' role ---
echo "Attempting to grant 'Editor' role (roles/editor) to the service account..."
echo "This is a broad role for troubleshooting. Ensure the authenticated gcloud user has permissions to manage IAM policies (e.g., Project IAM Admin or Owner)."

if ! gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:${SERVICE_ACCOUNT_ID}" \
    --role="roles/editor" \
    --condition=None; then
    echo "Error: Failed to grant 'roles/editor' to the service account."
    echo "This indicates a fundamental issue with IAM policy binding in your project."
    echo "Possible reasons:"
    echo "  - Incorrect Project ID."
    echo "  - Insufficient permissions for the gcloud user running this script."
    echo "  - Very specific organizational policies restricting ANY role bindings."
    echo "Please verify these points in the Google Cloud Console (IAM & Admin)."
    exit 1
fi
echo "Role 'roles/editor' binding command executed successfully."

# --- VERIFICATION OF ROLE BINDING ---
echo "Verifying that 'roles/editor' was successfully bound to the service account..."
# Fetch the IAM policy and check for the service account and role
if gcloud projects get-iam-policy "$GCP_PROJECT_ID" \
    --flatten="bindings[].members" \
    --format="json(bindings.role,bindings.members)" \
    --filter="bindings.role=roles/editor AND bindings.members=serviceAccount:${SERVICE_ACCOUNT_ID}" | grep -q "${SERVICE_ACCOUNT_ID}"; then
    echo "Verification successful: 'roles/editor' is confirmed to be bound to ${SERVICE_ACCOUNT_ID}."
else
    echo "Verification FAILED: 'roles/editor' does NOT appear to be bound to ${SERVICE_ACCOUNT_ID}."
    echo "This indicates a problem with the role binding, even if the command didn't error out."
    echo "Please manually check IAM & Admin -> IAM in your project to confirm the role assignment."
    exit 1
fi

# Final delay after verification, before generating key
echo "Role binding verified. Waiting an additional 10 seconds for global propagation before key generation..."
sleep 10

# --- 5. Generate and save the JSON key file ---
CREDENTIALS_FILE="credentials-tts.json"

echo "Generating JSON key for the service account and saving to ${CREDENTIALS_FILE}..."
if ! gcloud iam service-accounts keys create "$CREDENTIALS_FILE" \
    --iam-account="$SERVICE_ACCOUNT_ID" \
    --project="$GCP_PROJECT_ID"; then
    echo "Error: Failed to generate JSON key for the service account. This could be due to insufficient permissions or an issue with the service account itself."
    exit 1
fi

echo "JSON key saved to: ${CREDENTIALS_FILE}"
echo "Setup complete! You can now use this file with your Python script."
echo "------------------------------------------------------------------"

echo "--- IMPORTANT: Next Steps ---"
echo "1. Run your Python script with the newly generated 'credentials-tts.json'."
echo "   It should now be able to use the Text-to-Speech API."
echo ""
echo "2. If your Python script now works, consider narrowing down permissions for security:"
echo "   a. Go to Google Cloud Console (IAM & Admin -> IAM) for your project."
echo "   b. Find the service account '${SERVICE_ACCOUNT_ID}'."
echo "   c. Try to change its role from 'Editor' to 'Cloud Text-to-Speech User' (roles/cloudtts.user)."
echo "      If this works manually in the console, it implies a CLI-specific issue for that role."
echo "   d. If 'Cloud Text-to-Speech User' still doesn't work, you might need to create a custom role"
echo "      with only the 'texttospeech.synthesize' permission."
echo ""
echo "3. If the Python script still fails with 'ensure that account has tts role' after this script's success:"
echo "   - Propagation can take time (up to several minutes). Wait longer and retry."
echo "   - Verify the service account and 'Editor' role are explicitly listed in IAM for your project."
echo "   - There might be an organizational policy restricting API usage or role assignments. Contact your GCP administrator."
echo "-------------------------------------------------------------------------------------"

