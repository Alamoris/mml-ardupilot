import os
import asyncio
os.environ['MAVLINK20'] = '1'
os.environ['MAVLINK_DIALECT'] = 'all'
import pymavlink.mavutil as mavutil
from pymavlink.dialects.v20 import common as mavlink

MAX_CHUNK_LENGTH = 40
DURATION_SCALE = 0.14


def get_next_command(s, start_index):
    """
    Reads the next MML command from s starting at start_index.
    A command is either:
      - A tempo command: 't' followed by digits.
      - A note/rest: one letter in [a,b,c,d,e,f,g,h,p] (case-insensitive),
        optionally a '#' for accidental, then digits.
    Returns a tuple (command_string, next_index).
    """
    if s[start_index].lower() == 't':
        i = start_index + 1
        while i < len(s) and s[i].isdigit():
            i += 1
        return s[start_index:i], i
    elif s[start_index].lower() in 'abcdefgpr':
        i = start_index + 1
        if i < len(s) and s[i] in ['#', '+', '-']:
            i += 1
        while i < len(s) and (s[i].isdigit() or s[i] == '.'):
            i += 1
        return s[start_index:i], i
    else:
        # Unknown character; return it and advance.
        return s[start_index], start_index + 1


def segment_mml(melody, max_length, prefix=''):
    """
    Splits the full MML melody string into segments no longer than max_length,
    ensuring that commands are not split. Each segment will start with the most
    recent tempo command.
    """
    segments = []
    current_segment = prefix
    index = 0
    melody_len = len(melody)

    while index < melody_len:
        cmd, next_index = get_next_command(melody, index)
        # If adding this command would exceed max_length, finish the current segment.
        if len(current_segment) + len(cmd) > max_length:
            segments.append(current_segment)
            # Start a new segment. If the command is not a tempo command, prepend the last tempo.
            current_segment = prefix + cmd
            index = next_index
        else:
            current_segment += cmd
            index = next_index

    if current_segment:
        segments.append(current_segment)
    return segments


def calculate_mml_duration(mml_segment, starting_tempo=120):
    """
    Parses the MML segment and computes an approximate playback duration (in seconds)
    using the formula:
        whole_note_duration = 240 / tempo   (seconds)
        note_duration = whole_note_duration / note_value
    (This raw calculation does not account for the firmware’s internal shortening.)
    Returns (total_duration, final_tempo).
    """

    print(f'CALC DUR WITH TEMPO: {starting_tempo}, segment: {mml_segment}')
    current_tempo = starting_tempo
    total_duration = 0.0
    index = 0
    while index < len(mml_segment):
        ch = mml_segment[index].lower()
        if ch == 't':  # tempo change
            index += 1
            tempo_digits = ""
            while index < len(mml_segment) and mml_segment[index].isdigit():
                tempo_digits += mml_segment[index]
                index += 1
            if tempo_digits:
                current_tempo = int(tempo_digits)
        elif ch in 'abcdefgpr':  # note or rest command
            index += 1
            if index < len(mml_segment) and mml_segment[index] in ['#', '+', '-']:
                index += 1

            num_str = ""
            while index < len(mml_segment) and mml_segment[index].isdigit():
                num_str += mml_segment[index]
                index += 1

            note_val = int(num_str) if num_str else 4
            duration = 240 / (current_tempo * note_val)

            dot_dur = duration * 0.5
            while index < len(mml_segment) and mml_segment[index] == '.':
                duration += dot_dur
                dot_dur *= 0.5
                index += 1

            total_duration += duration
        else:
            index += 1
    return total_duration, current_tempo


async def send_segment(conn, segment):
    """
    Sends one MML segment to the drone via MAVLink.
    """
    print('play tune', segment.encode('utf-8'), len(segment.encode('utf-8')))
    conn.mav.play_tune_send(1, 1, "".encode('utf-8'), segment.encode('utf-8'))


async def play_tune_async(conn, melody, max_length=MAX_CHUNK_LENGTH, tempo=120, volume=None):
    if not tempo or not isinstance(tempo, int) or tempo > 255:
        raise ValueError('Wrong tempo value')

    segment_prefix = f't{tempo}'
    if volume:
        segment_prefix += f'v{volume} '

    segments = segment_mml(melody, max_length, prefix=segment_prefix)

    print("Segmented MML Commands:")
    for i, seg in enumerate(segments):
        print(f"Segment {i + 1}: {seg}, {len(seg)}")

    starting_tempo = tempo
    for i, segment in enumerate(segments):
        raw_duration, ending_tempo = calculate_mml_duration(segment[len(segment_prefix):], starting_tempo)
        wait_time = (raw_duration * DURATION_SCALE) + 0.1  # add a small 0.1 sec buffer
        print(f"Sending segment {i + 1} (raw duration: {raw_duration:.2f} sec, waiting {wait_time:.2f} sec)")
        await send_segment(conn, segment)
        await asyncio.sleep(raw_duration)
        starting_tempo = ending_tempo
    print("Finished sending all segments.")


def main():
    # Set MAVLink environment variables.
    os.environ['MAVLINK20'] = '1'
    os.environ['MAVLINK_DIALECT'] = 'all'
    # Establish MAVLink connection.
    real_link = 'udpout:192.168.0.123:14561'
    src_system = mavlink.MAV_COMP_ID_USER1
    conn = mavutil.mavlink_connection(real_link, baud=115200,
                                      source_system=90,
                                      source_component=src_system)

    tempo = 60
    volume = 14
    melody = (
        "a4r1^1a4"
        # "f+8g+16r16c+16d+8< b32r32> d16c+16< b16r16b16r16> c+8d16r16d32r32c+32r32< b16> c+16d+16f+16g+16d+16f+16c+16d16< b16> c+16< b16> d+8f+16r16g+16d+16f+16c+16d16< b16> c+16d+16d16c+16< b16> c+16d16r16< b16> c+16d16f+16c+16d16c+16< b16> c+16r16< b16r16> c+16r16f+8g+16r16c+16d+8< b32r32> d16c+16< b16r16b16r16> c+8d16r16d32r32c+32r32< b16> c+16d+16f+16g+16d+16f+16c+16d16< b16> c+16< b16> d+8f+16r16g+16d+16f+16c+16d16< b16> c+16d+16d16c+16< b16> c+16d16r16< b16> c+16d16f+16c+16d16c+16< b16> c+8< b16r16b16r16b16r16f+16g+16b16r16f+16g+16b16> c+16d+16c+16e16d+16e16f+16< b16r16b16r16f+16g+16b16g+16> e16d+16c+16< b16f+16d+16e16f+16b16r16f+16g+16b16r16f+16g+16b16b16> c+16d+16< b16f+16g+16f+16b8b16a+16b16f+16g+16b16> e16d+16e16f+16< b16r16a+16r16b16r16f+16g+16b16r16f+16g+16b16> c+16d+16c+16e16d+16e16f+16< b16r16b16r16f+16g+16b16g+16> e16d+16c+16< b16f+16d+16e16f+16b16r16f+16g+16b16r16f+16g+16b16b16> c+16d+16< b16f+16g+16f+16b8b16a+16b16f+16g+16b16> e16d+16e16f+16< b8> c+8f+8g+16r16c+16d+8< b32r32> d16c+16< b16r16b16r16> c+8d16r16d32r32c+32r32< b16> c+16d+16f+16g+16d+16f+16c+16d16< b16> c+16< b16> d+8f+16r16g+16d+16f+16c+16d16< b16> c+16d+16d16c+16< b16> c+16d16r16< b16> c+16d16f+16c+16d16c+16< b16> c+16r16< b16r16> c+16r16f+8g+16r16c+16d+8< b32r32> d16c+16< b16r16b16r16> c+8d16r16d32r32c+32r32< b16> c+16d+16f+16g+16d+16f+16c+16d16< b16> c+16< b16> d+8f+16r16g+16d+16f+16c+16d16< b16> c+16d+16d16c+16< b16> c+16d16r16< b16> c+16d16f+16c+16d16c+16< b16> c+8< b16r16b16r16b16r16f+16g+16b16r16f+16g+16b16> c+16d+16c+16e16d+16e16f+16< b16r16b16r16f+16g+16b16g+16> e16d+16c+16< b16f+16d+16e16f+16b16r16f+16g+16b16r16f+16g+16b16b16> c+16d+16< b16f+16g+16f+16b8b16a+16b16f+16g+16b16> e16d+16e16f+16< b16r16a+16r16b16r16f+16g+16b16r16f+16g+16b16> c+16d+16c+16e16d+16e16f+16< b16r16b16r16f+16g+16b16g+16> e16d+16c+16< b16f+16d+16e16f+16b16r16f+16g+16b16r16f+16g+16b16b16> c+16d+16< b16f+16g+16f+16b8b16a+16b16f+16g+16b16> e16d+16e16f+16< b8> c+8<< e8> e8< f+8> f+8< d+8> d+8< g+8> g+8< c+8> c+8< f+8> f+8<< b8> b8< b8> b8e8> e8< f+8> f+8< d+8> d+8< g+8> g+8< c+8> c+8< f+8> f+8<< b8> b8< b8> b8e8> e8< f+8> f+8< d+8> d+8< g+8> g+8< c+8> c+8< f+8> f+8<< b8> b8< b8> b8e8> e8< f+8> f+8< d+8> d+8< g+8> g+8< c+8> c+8< f+8> f+8<< b8> b8< b8> b8e8g+8b8> e8< d+8f+8b8> d+8< c+8e8g+8b8< b8> d+8f+8b8e8g+8b8> e8< d+8f+8b8> d+8< c+8e8g+8b8< b8> d+8f+8b8e8g+8b8> e8< d+8f+8b8> d+8< c+8e8g+8b8< b8> d+8f+8b8e8g+8b8> e8< d+8f+8b8> d+8< c+8e8g+8b8< b8> d+8f+8b8e8> e8< f+8> f+8< d+8> d+8< g+8> g+8< c+8> c+8< f+8> f+8<< b8> b8< b8> b8e8> e8< f+8> f+8< d+8> d+8< g+8> g+8< c+8> c+8< f+8> f+8<< b8> b8< b8> b8e8> e8< f+8> f+8< d+8> d+8< g+8> g+8< c+8> c+8< f+8> f+8<< b8> b8< b8> b8e8> e8< f+8> f+8< d+8> d+8< g+8> g+8< c+8> c+8< f+8> f+8<< b8> b8< b8> b8e8g+8b8> e8< d+8f+8b8> d+8< c+8e8g+8b8< b8> d+8f+8b8e8g+8b8> e8< d+8f+8b8> d+8< c+8e8g+8b8< b8> d+8f+8b8e8g+8b8> e8< d+8f+8b8> d+8< c+8e8g+8b8< b8> d+8f+8b8e8g+8b8> e8< d+8f+8b8> d+8< c+8e8g+8b8< b8> d+8f+8b8>> d+16e16f+8b8d+16e16f+16b16> c+16d+16c+16< a+16b8f+8d+16e16f+8b16> c+8< a+16b16> c+16e16d+16e16c+16"
    )

    #d5p24d8p384d5p24d8p384d5p24d8p384d8p384d8p384d8p384d5p24d8p384d5p24d8p384d5p24d8p384d8p384d8p384d8p384d5p24d8p384d5p24d8p384d5p24d8p384d8p384a8p384c8p384f5a5d5p24f5a5d5p24f8a8d8p384a8c8e8p384a#5d5f5p24a#5d5f5p24a#8d8f8p384d8g8p384a5c5e5p24a5c5e5p24a8d8p384g8c8p384a8c8p384a5d5p6a8p384c8p384f5a#5d5p24f5a#5d5p24a#8d8p384a#8e8p384a5c5f5p24a5c5f5p24c8f8p384c8g8p384c5e5p24c5e5p24a8d8p384c8p384f5a5d5p3a8p384c8p384f5a5d5p24f5a5d5p24a8d8p384a8f8p384a#5d5g5p24a#5d5g5p24d8g8p384d8a8p384d5g5a#5p24d5g5a#5p24f8a8p384e8g8p384f8a8p384d5p6d8p384e8p384a#5d5f5p24a#5d5f5p24a#5d5g5p24f8a8p384d5p6d8p384f8p384a5c#5e5p24a5c#5e5p24d8f8p384h8d8p384a8c#8e8p3a8p384c8p384f5a5d5p24f5a5d5p24f8a8d8p384a8c8e8p384a#5d5f5p24a#5d5f5p24a#8d8f8p384d8g8p384a5c5e5p24a5c5e5p24a8d8p384g8c8p384a8c8p384a5d5p6a8p384c8p384f5a#5d5p24f5a#5d5p24a#8d8p384a#8e8p384a5c5f5p24a5c5f5p24c8f8p384c8g8p384c5e5p24c5e5p24a8d8p384c8p384f5a5d5p3a8p384c8p384f5a5d5p24f5a5d5p24a8d8p384a8f8p384a#5d5g5p24a#5d5g5p24d8g8p384d8a8p384d5g5a#5p24d5g5a#5p24f8a8p384e8g8p384f8a8p384d5p6d8p384e8p384a#5d5f5p24a#5d5f5p24a#5d5g5p24f8a8p384d5p6d8p384f8p384a5c#5e5p24a5c#5e5p24d8p384c#8p384a5d5p24a5d5p24a5c5e5p24c5d5f5p24f8p384f8p384a#5d5g5p24d8a8p384f8p4a8f8p384a8d8p384a8p2d8g8a#8p3a#8g8p384a#8d8p384a#8p2c#8e8p384c#5e5p24g3d3p24a3c#3f3p6f8p384g8p384d5f5a5p24d5f5a5p24d5f5a5p24d8f8a#8p384d8f8a8p2c5e5g5p24c5e5g5p24c5e5g5p24c8e8g8p384c8f8a8p2d5f5a5p24d5f5a5p24d5f5a5p24d8f8a#8p384d8f8a8p2c#5e5g5p24c#5f5p24a5e5p24f5a5d5p3d8p384e8p384a2d2f2p16g8p384a8p384c5g5p24c5f5p24c5e5p24a5c5f5p24a5c5g5p24a5c5a5p24c5e5g5p3f8p384g8p384c5f5a5p3g8p384f8p384c#5e5p24c#5f5p24c#5e5p24f5a5d5p3e8p384c8p384f8a8d8p3d8p384e8p384a5d5f5p3e8p384f8p384c5g5p24c5f5p24c5g5p24f5a5p24c5g5p24c5f5p24f5a#5d5p3d8p384e8p384a5d5f5p24a5d5g5p24d5a5p24a#5d5a#5p24a#5d5p24a#5g5p24a5f5p3g8p384e8p384a5d5p3e8p384c#8p384d5f5a5p2d5g5a#5p2c5f5a5p24c5f5a5p24c5f5a5p24c8e8a8p384g8p2a#5d5g5p2a5d5f5p2a5f5p24a5g5p24a5e5p24f3a3d3p24d8p384e8p384f8p384d3f3a3p24d8p384e8p384f8p384d3f3a#3p24d8p384e8p384f8p384c5f5a5p24c5f5a5p24f5c5p24c8e8a8p384g8p2a#5d5g5p2a5d5f5p2a5f5p24a5g5p24a5e5p24f3a3d3p2d1
    # boom e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1p8e8g1p8g8e1p8a8g8a8g8a8g8a8g8a8b1
    # nyan f+4 g+8 r8 c+8 d+4 < b16 r16 > d8 c+8 < b8 r8 b8 r8 > c+4 d8 r8 d16 r16 c+16 r16 < b8 > c+8 d+8 f+8 g+8 d+8 f+8 c+8 d8 < b8 > c+8 < b8 > d+4 f+8 r8 g+8 d+8 f+8 c+8 d8 < b8 > c+8 d+8 d8 c+8 < b8 > c+8 d8 r8 < b8 > c+8 d8 f+8 c+8 d8 c+8 < b8 > c+8 r8 < b8 r8 > c+8 r8 f+4 g+8 r8 c+8 d+4 < b16 r16 > d8 c+8 < b8 r8 b8 r8 > c+4 d8 r8 d16 r16 c+16 r16 < b8 > c+8 d+8 f+8 g+8 d+8 f+8 c+8 d8 < b8 > c+8 < b8 > d+4 f+8 r8 g+8 d+8 f+8 c+8 d8 < b8 > c+8 d+8 d8 c+8 < b8 > c+8 d8 r8 < b8 > c+8 d8 f+8 c+8 d8 c+8 < b8 > c+4 < b8 r8 b8 r8 b8 r8 f+8 g+8 b8 r8 f+8 g+8 b8 > c+8 d+8 c+8 e8 d+8 e8 f+8 < b8 r8 b8 r8 f+8 g+8 b8 g+8 > e8 d+8 c+8 < b8 f+8 d+8 e8 f+8 b8 r8 f+8 g+8 b8 r8 f+8 g+8 b8 b8 > c+8 d+8 < b8 f+8 g+8 f+8 b4 b8 a+8 b8 f+8 g+8 b8 > e8 d+8 e8 f+8 < b8 r8 a+8 r8 b8 r8 f+8 g+8 b8 r8 f+8 g+8 b8 > c+8 d+8 c+8 e8 d+8 e8 f+8 < b8 r8 b8 r8 f+8 g+8 b8 g+8 > e8 d+8 c+8 < b8 f+8 d+8 e8 f+8 b8 r8 f+8 g+8 b8 r8 f+8 g+8 b8 b8 > c+8 d+8 < b8 f+8 g+8 f+8 b4 b8 a+8 b8 f+8 g+8 b8 > e8 d+8 e8 f+8 < b4 > c+4 f+4 g+8 r8 c+8 d+4 < b16 r16 > d8 c+8 < b8 r8 b8 r8 > c+4 d8 r8 d16 r16 c+16 r16 < b8 > c+8 d+8 f+8 g+8 d+8 f+8 c+8 d8 < b8 > c+8 < b8 > d+4 f+8 r8 g+8 d+8 f+8 c+8 d8 < b8 > c+8 d+8 d8 c+8 < b8 > c+8 d8 r8 < b8 > c+8 d8 f+8 c+8 d8 c+8 < b8 > c+8 r8 < b8 r8 > c+8 r8 f+4 g+8 r8 c+8 d+4 < b16 r16 > d8 c+8 < b8 r8 b8 r8 > c+4 d8 r8 d16 r16 c+16 r16 < b8 > c+8 d+8 f+8 g+8 d+8 f+8 c+8 d8 < b8 > c+8 < b8 > d+4 f+8 r8 g+8 d+8 f+8 c+8 d8 < b8 > c+8 d+8 d8 c+8 < b8 > c+8 d8 r8 < b8 > c+8 d8 f+8 c+8 d8 c+8 < b8 > c+4 < b8 r8 b8 r8 b8 r8 f+8 g+8 b8 r8 f+8 g+8 b8 > c+8 d+8 c+8 e8 d+8 e8 f+8 < b8 r8 b8 r8 f+8 g+8 b8 g+8 > e8 d+8 c+8 < b8 f+8 d+8 e8 f+8 b8 r8 f+8 g+8 b8 r8 f+8 g+8 b8 b8 > c+8 d+8 < b8 f+8 g+8 f+8 b4 b8 a+8 b8 f+8 g+8 b8 > e8 d+8 e8 f+8 < b8 r8 a+8 r8 b8 r8 f+8 g+8 b8 r8 f+8 g+8 b8 > c+8 d+8 c+8 e8 d+8 e8 f+8 < b8 r8 b8 r8 f+8 g+8 b8 g+8 > e8 d+8 c+8 < b8 f+8 d+8 e8 f+8 b8 r8 f+8 g+8 b8 r8 f+8 g+8 b8 b8 > c+8 d+8 < b8 f+8 g+8 f+8 b4 b8 a+8 b8 f+8 g+8 b8 > e8 d+8 e8 f+8 < b4 > c+4 << e4 > e4 < f+4 > f+4 < d+4 > d+4 < g+4 > g+4 < c+4 > c+4 < f+4 > f+4 << b4 > b4 < b4 > b4 e4 > e4 < f+4 > f+4 < d+4 > d+4 < g+4 > g+4 < c+4 > c+4 < f+4 > f+4 << b4 > b4 < b4 > b4 e4 > e4 < f+4 > f+4 < d+4 > d+4 < g+4 > g+4 < c+4 > c+4 < f+4 > f+4 << b4 > b4 < b4 > b4 e4 > e4 < f+4 > f+4 < d+4 > d+4 < g+4 > g+4 < c+4 > c+4 < f+4 > f+4 << b4 > b4 < b4 > b4 e4 g+4 b4 > e4 < d+4 f+4 b4 > d+4 < c+4 e4 g+4 b4 < b4 > d+4 f+4 b4 e4 g+4 b4 > e4 < d+4 f+4 b4 > d+4 < c+4 e4 g+4 b4 < b4 > d+4 f+4 b4 e4 g+4 b4 > e4 < d+4 f+4 b4 > d+4 < c+4 e4 g+4 b4 < b4 > d+4 f+4 b4 e4 g+4 b4 > e4 < d+4 f+4 b4 > d+4 < c+4 e4 g+4 b4 < b4 > d+4 f+4 b4 e4 > e4 < f+4 > f+4 < d+4 > d+4 < g+4 > g+4 < c+4 > c+4 < f+4 > f+4 << b4 > b4 < b4 > b4 e4 > e4 < f+4 > f+4 < d+4 > d+4 < g+4 > g+4 < c+4 > c+4 < f+4 > f+4 << b4 > b4 < b4 > b4 e4 > e4 < f+4 > f+4 < d+4 > d+4 < g+4 > g+4 < c+4 > c+4 < f+4 > f+4 << b4 > b4 < b4 > b4 e4 > e4 < f+4 > f+4 < d+4 > d+4 < g+4 > g+4 < c+4 > c+4 < f+4 > f+4 << b4 > b4 < b4 > b4 e4 g+4 b4 > e4 < d+4 f+4 b4 > d+4 < c+4 e4 g+4 b4 < b4 > d+4 f+4 b4 e4 g+4 b4 > e4 < d+4 f+4 b4 > d+4 < c+4 e4 g+4 b4 < b4 > d+4 f+4 b4 e4 g+4 b4 > e4 < d+4 f+4 b4 > d+4 < c+4 e4 g+4 b4 < b4 > d+4 f+4 b4 e4 g+4 b4 > e4 < d+4 f+4 b4 > d+4 < c+4 e4 g+4 b4 < b4 > d+4 f+4 b4 >> d+8 e8 f+4 b4 d+8 e8 f+8 b8 > c+8 d+8 c+8 < a+8 b4 f+4 d+8 e8 f+4 b8 > c+4 < a+8 b8 > c+8 e8 d+8 e8 c+8
    asyncio.run(play_tune_async(
        conn,
        melody,
        tempo=tempo,
        volume=volume
    ))


if __name__ == '__main__':
    main()
