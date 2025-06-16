#!/bin/bash

AUDIO_DIR="./texts/audio"
SILENCE_FILE="./silence-0.2s.wav"
MAX_DURATION=488  # 8 minutes 8 seconds
MERGE_PREFIX="files-to-merge"
OUTPUT_PREFIX="output"

# Remove previous outputs
rm -f ${MERGE_PREFIX}-*.txt ${OUTPUT_PREFIX}-*.wav

# Ensure silence file exists
if [ ! -f "$SILENCE_FILE" ]; then
  echo "ERROR: Missing $SILENCE_FILE in current directory."
  exit 1
fi

# Function to get duration
get_duration() {
  ffprobe -v error -select_streams a:0 -show_entries stream=duration \
    -of default=noprint_wrappers=1:nokey=1 "$1"
}

# Get audio files (excluding silence), sorted
mapfile -t audio_files < <(find "$AUDIO_DIR" -type f -name "*.wav" | sort)

# Get silence duration (~0.2s)
silence_duration=$(get_duration "$SILENCE_FILE")
pause_block_duration=$(echo "$silence_duration * 2" | bc)  # ~0.4s between files

# Silence padding durations
start_silence_duration=$(echo "$silence_duration * 5" | bc)  # 1s at start
end_extra_silence_duration=$(echo "$silence_duration * 3" | bc)  # 0.6s extra at end

index=1
current_duration=0
list_file="${MERGE_PREFIX}-${index}.txt"
touch "$list_file"

# Add 1s silence at start
for i in {1..5}; do
  echo "file '$SILENCE_FILE'" >> "$list_file"
done
current_duration=$(echo "$current_duration + $start_silence_duration" | bc)

# Loop through audio files
for file in "${audio_files[@]}"; do
  duration=$(get_duration "$file")
  total_block_duration=$(echo "$duration + $pause_block_duration" | bc)

  new_total=$(echo "$current_duration + $total_block_duration + $end_extra_silence_duration" | bc)
  if (( $(echo "$new_total > $MAX_DURATION" | bc -l) )); then
    # Add final 0.6s (3x silence) to previous list before moving on
    for i in {1..3}; do
      echo "file '$SILENCE_FILE'" >> "$list_file"
    done

    index=$((index + 1))
    list_file="${MERGE_PREFIX}-${index}.txt"
    touch "$list_file"

    # Add 1s silence at start of new list
    for i in {1..5}; do
      echo "file '$SILENCE_FILE'" >> "$list_file"
    done
    current_duration=$start_silence_duration
  fi

  echo "file '$file'" >> "$list_file"
  echo "file '$SILENCE_FILE'" >> "$list_file"
  echo "file '$SILENCE_FILE'" >> "$list_file"
  current_duration=$(echo "$current_duration + $total_block_duration" | bc)
done

# Add 0.6s silence at the end of the final list
for i in {1..3}; do
  echo "file '$SILENCE_FILE'" >> "$list_file"
done

# Merge all lists into output WAVs
for f in ${MERGE_PREFIX}-*.txt; do
  num=$(echo "$f" | grep -oP '\d+')
  ffmpeg -y -f concat -safe 0 -i "$f" -c copy "${OUTPUT_PREFIX}-${num}.wav"
done

echo "✅ All output files created with proper start/end silences."

