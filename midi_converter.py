import mido
import sys

# Map MIDI pitch classes (ignoring octave) to MML note letters.
import mido
import sys

# Map MIDI pitch classes (ignoring octave) to MML note letters.
NOTE_MAP = {
    0: 'c', 1: 'c#', 2: 'd', 3: 'd#', 4: 'e',
    5: 'f', 6: 'f#', 7: 'g', 8: 'g#', 9: 'a', 10: 'a#', 11: 'b'
}


def note_to_mml(midi_note):
    """Convert a MIDI note number to an MML note (ignoring octave)."""
    return NOTE_MAP[midi_note % 12]


def duration_to_mml_length(duration_ticks, ticks_per_beat):
    """
    Convert a duration in ticks to an MML note length.
    Assumes that a quarter note is represented as '4'.
    For example, if a note lasts one beat (quarter note) the output is '4'.
    """
    if duration_ticks <= 0:
        return 4  # default to quarter note if duration is 0 or negative
    beats = duration_ticks / ticks_per_beat
    # Calculate the MML length value.
    note_value = 4 / beats
    # Round to the nearest integer (common values: 1, 2, 4, 8, etc.)
    return int(round(note_value))


def midi_to_mml(midi_file, debug=True):
    """
    Convert a MIDI file to an MML string using only the first track.

    This function:
      - Loads the MIDI file and selects only the first track.
      - Processes note_on and note_off events to determine each note's start time and duration.
      - Inserts rests (denoted by 'p') when there's a gap between notes.
      - Flushes any lingering note_on events at the end.
    """
    mid = mido.MidiFile(midi_file)
    ticks_per_beat = mid.ticks_per_beat
    if debug:
        print("Ticks per beat:", ticks_per_beat)

    # Use only the first track (instead of merging all tracks).
    track = mid.tracks[2]
    # print(track, len(mid.tracks))
    current_tick = 0
    notes = []  # List to hold completed notes: { 'note': MIDI note, 'start': tick, 'end': tick }
    pending_notes = {}  # Dictionary to hold currently active (pending) note_on events

    # Process each MIDI message in the first track.
    for msg in track:
        current_tick += msg.time
        if debug:
            print(f"Tick: {current_tick}, Message: {msg}")
        if msg.type == 'note_on' and msg.velocity > 0:
            pending_notes.setdefault(msg.note, []).append(current_tick)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            if msg.note in pending_notes and pending_notes[msg.note]:
                start_tick = pending_notes[msg.note].pop(0)
                notes.append({
                    'note': msg.note,
                    'start': start_tick,
                    'end': current_tick
                })

    # Flush any pending notes that didn't receive a corresponding note_off.
    for note, start_times in pending_notes.items():
        for start_tick in start_times:
            notes.append({
                'note': note,
                'start': start_tick,
                'end': current_tick
            })
            if debug:
                print(f"Flushed note {note} from tick {start_tick} to {current_tick}")

    # Sort the notes in order of their start times.
    notes.sort(key=lambda n: n['start'])

    mml = ""
    last_end = 0
    for note_event in notes:
        # Insert a rest ('p') if there's a gap between the previous note and this one.
        if note_event['start'] > last_end:
            gap = note_event['start'] - last_end
            rest_length = duration_to_mml_length(gap, ticks_per_beat)
            mml += f"p{rest_length}"
        # Convert the MIDI note to an MML note letter.
        note_letter = note_to_mml(note_event['note'])
        duration = note_event['end'] - note_event['start']
        print('duration_to_mml_length', duration, ticks_per_beat)
        note_length = duration_to_mml_length(duration, ticks_per_beat)
        mml += f"{note_letter}{note_length}"
        last_end = note_event['end']

    return mml

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python midi_to_mml.py <input_midi_file>")
        sys.exit(1)

    midi_file = sys.argv[1]
    # Set debug=True to see detailed processing information.
    debug = True
    mml_string = midi_to_mml(midi_file, debug)
    print("Generated MML String:")
    print(mml_string)


""" boomer
e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1
p0e8g8b8p8e8g8b8e8g8b8p8e8g8b8b8g8e8p8e8g8c8p8c8g8e8e8g8c8p8e8g8c8e8g8c8p8e8c8a8p8e8c8a8a8e8c8p8e8c8a8a8e8c8p8e8g8c8p8e8g8c8e8g8c8p8e8g8c8e8g8c8p8e8g8b8p8e8g8b8e8g8b8p8e8g8b8b8g8e8p8e8g8c8p8c8g8e8e8g8c8p8e8g8c8e8g8c8p8e8c8a8p8e8c8a8a8e8c8p8e8c8a8a8e8c8p8e8g8c8p8e8g8c8e8g8c8p8e8g8c8e8g8c8p8e8g8b8p8e8g8b8e8g8b8p8e8g8b8b8g8e8p8e8g8c8p8c8g8e8e8g8c8p8e8g8c8e8g8c8p8e8c8a8p8e8c8a8a8e8c8p8e8c8a8a8e8c8p8e8g8c8p8e8g8c8e8g8c8p8e8g8c8e8g8c8p8e8g8b8p8e8g8b8e8g8b8p8e8g8b8b8g8e8p8e8g8c8p8c8g8e8e8g8c8p8e8g8c8e8g8c8p8e8c8a8p8e8c8a8a8e8c8p8e8c8a8a8e8c8p8e8g8c8p8e8g8c8e8g8c8p8e8g8c8e8g8c8p8e8g8b8p8e8g8b8e8g8b8p8e8g8b8b8g8e8p8e8g8c8p8c8g8e8e8g8c8p8e8g8c8e8g8c8p8e8c8a8p8e8c8a8a8e8c8p8e8c8a8a8e8c8p8e8g8c8p8e8g8c8e8g8c8p8e8g8c8e8g8c8p0e8g8b8p8e8g8b8e8g8b8p8e8g8b8b8g8e8p8e8g8c8p8c8g8e8e8g8c8p8e8g8c8e8g8c8p8e8c8a8p8e8c8a8a8e8c8p8e8c8a8a8e8c8p8e8g8c8p8e8g8c8e8g8c8p8e8g8c8e8g8c8p8e8g8b8p8e8g8b8e8g8b8p8e8g8b8b8g8e8p8e8g8c8p8c8g8e8e8g8c8p8e8g8c8e8g8c8p8e8c8a8p8e8c8a8a8e8c8p8e8c8a8a8e8c8p8e8g8c8p8e8g8c8e8g8c8p8e8g8c8e8g8c8
"""

