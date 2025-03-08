import os
import time
import asyncio
os.environ['MAVLINK20'] = '1'
os.environ['MAVLINK_DIALECT'] = 'all'
import pymavlink.mavutil as mavutil
from pymavlink.dialects.v20 import common as mavlink

import threading


MAX_CHUNK_LENGTH = 30


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
        while i < len(s) and s[i].isdigit():
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

    print('CALC DUR WITH TEMPO', starting_tempo)
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
            total_duration += duration
        else:
            index += 1
    return total_duration, current_tempo


def send_segment(conn, segment):
    """
    Sends one MML segment to the drone via MAVLink.
    """
    print('play tune', segment.encode('utf-8'), len(segment.encode('utf-8')))
    conn.mav.play_tune_send(1, 1, "".encode('utf-8'), segment.encode('utf-8'))


def play_tune(conn, melody, max_length=MAX_CHUNK_LENGTH, tempo=120, volume=None):
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
        raw_duration, ending_tempo = calculate_mml_duration(segment, starting_tempo)
        print(f"Sending segment {i + 1} (raw duration: {raw_duration:.2f} sec")
        send_segment(conn, segment)
        time.sleep(raw_duration)
        starting_tempo = ending_tempo
    print("Finished sending all segments.")


def main():
    # Establish MAVLink connection.
    real_link = 'udpout:192.168.0.160:14561'
    src_system = mavlink.MAV_COMP_ID_USER1
    conn = mavutil.mavlink_connection(real_link, baud=115200,
                                      source_system=90,
                                      source_component=src_system)

    real_link_2 = 'udpout:192.168.0.113:14561'
    src_system_2 = mavlink.MAV_COMP_ID_USER1
    conn_2 = mavutil.mavlink_connection(real_link_2, baud=115200,
                                        source_system=90,
                                        source_component=src_system_2)

    real_link_3 = 'udpout:192.168.0.175:14560'
    src_system_3 = mavlink.MAV_COMP_ID_USER1
    conn_3 = mavutil.mavlink_connection(real_link_3, baud=115200,
                                        source_system=90,
                                        source_component=src_system_3)


    tempo = 140
    volume = 40
    melodies = [
        "a1r8c+8<b8>c+8d8c+8<b8>c+8a1r8d8c+8d8e8d8c+8d8a8r1d8c+8d8e8d8c+8d8g+8r4r8a16r8r16b16r16g+16r8r16c+8<b8>c+8d8c+8<b8>c+8",
        "a8r4a8r4a8r8a8r4a8r4a8r8>d8r4d8r4d8r8d8r4<f+8r4>d8r8<b8r4b8r4b8r8b8r4b8r4b8r8e8r4e8r4e8r8e8r4e8r4e8r8",
        "f+8r4f+8r4f+8r8f+8r4f+8r4f+8r8b8r4b8r4b8r8b8r4b8r4b8r8g+8r4g+8r4g+8r8g+8r4g+8r4g+8r8>c+8r4c+8r4c+8r8c+8r4c+8r4c+8r8"
    ]


    t1 = threading.Thread(target=play_tune, args=(conn, melodies[0], MAX_CHUNK_LENGTH, tempo, volume))
    t1.start()
    t2 = threading.Thread(target=play_tune, args=(conn_2, melodies[1], MAX_CHUNK_LENGTH, tempo, volume * 2))
    t2.start()
    t3 = threading.Thread(target=play_tune, args=(conn_3, melodies[2], MAX_CHUNK_LENGTH, tempo, volume * 2))
    t3.start()


if __name__ == '__main__':
    main()


'''
    SLEDSTVIE
    melodies = [
        "a1r8c+8<b8>c+8d8c+8<b8>c+8a1r8d8c+8d8e8d8c+8d8a8r1d8c+8d8e8d8c+8d8g+8r4r8a16r8r16b16r16g+16r8r16c+8<b8>c+8d8c+8<b8>c+8",
        "a8r4a8r4a8r8a8r4a8r4a8r8>d8r4d8r4d8r8d8r4<f+8r4>d8r8<b8r4b8r4b8r8b8r4b8r4b8r8e8r4e8r4e8r8e8r4e8r4e8r8",
        "f+8r4f+8r4f+8r8f+8r4f+8r4f+8r8b8r4b8r4b8r8b8r4b8r4b8r8g+8r4g+8r4g+8r8g+8r4g+8r4g+8r8>c+8r4c+8r4c+8r8c+8r4c+8r4c+8r8"
    ]

    #PIRATES
    melodies = [
        "r1r1r1r1r2d4d4d8e8f4f4f8r8e4e4r1d4d4r4f4f4r4e4e4r4d4r2d4d4r4g4g4r4a+4a+4r1f4f4g4r2r4e4e4r4e4e8r4r8>d4d4d8e8f4f4f8r8e4e4r1d4d4r4f4f4r1d4r2d4d4r4g4g4r4a+4a+4r1f4f4g4r2r4e4e4r2r4e4f4r4g4r1r2a+8r1r1r8<f4f16r4r8r16a8a16r16a8a16r16a8a16r16a+8a8r2g8g16r16g8g16r16g8g16r16g8a8r2a8a16r16a8a16r16a8a16r16a+8a8r2g8g16r2r16d8d16r2r16f4f8f16r1r16f8f16r16g8g16r16a8a16r16g8g16r2r16a8a16r1r4r16d8d16r2r16d8r2r8>f8f16r1r1r16d8d16r2r16f8f16r16g8g16r4r16a+8a+16r1r1r16a8a16r2r16a+8a+16r2r16a8a16r16a8a16r16a8a16r16a8r2r8g8g16r2r16f8f16r1r4r16d4d16r4r8r16a4a16r4r8r16a+4a+16r4r8r16a8a16r16a8a16r4r16a8r2r8g8g16r2r16f8f16r1r4r16d4d16r1r1r2r8r16",
        "r1r1r1r1r2a4a4a8>c8d4d4d8g8c4c4d8c8c8d4r4r8<a+4a+4>d8e8c4c4f8g8c4c4d8c8<a4r2a4a4>d8f8d4d4g8a8g4g4a8g8a8r2r8d4d4d4a8r2r8c+4c+4f8d8c+4c+8r4r8a4a4a8>c8d4d4d8g8c4c4d8c8c8d8d16r4r8r16<a+4a+4>d8e8c4c4f8g8e4e4d8r8<a4r2a4a4>d8f8d4d4g8a8g4g4a8g8a8r2r8d4d4d4a8r2r8c+4c+4r4d4d4c4d4r4d4a8r4r8f8d8r2r4g8r4r8g8d8r2r4<e8e8e16r16d4d16r16c+4c+16r4r8r16f8f16r16f8f16r16f8f16r16f8f8r2e8e16r16e8e16r16e8e16r16e8f8r2f8f16r16f8f16r16f8f16r16f8f8r2e8e16r16f8f16r16e8e16r16<a8a16r2r16>d4d8d16r4r16g8g16r16f8f16r16e8e16r16c8c16r16c8c16r16c8c16r16e8e16r2r16f8f16r2r16e8e16r16f8f16r16e8e16r16<a8a16r2r16a8r2r8>>d8d16r2r16g8g16r16f8f16r16g8g16r16a8a16r16g8g16r16f8f16r16<a+8a+16r2r16>d8d16r16d8d16r16a8a16r16d8d16r16d8d16r16g8g16r16f8f16r2r16d8d16r2r16f8f16r2r16g8g16r2r16f8f16r16f8f16r16f8f16r16e8r2r8d8d16r2r16d8d16r2r16f8f16r16g8g16r16e8e16r16<a4a16r4r8r16>f4f16r4r8r16f4f16r4r8r16f8f16r16f8f16r16>c8c16r16<e8r2r8d8d16r2r16d8d16r2r16f8f16r16g8g16r16e8e16r16<a4a16r1r1r2r8r16",
        "d4d8d4d8d4d8d8d8d8d4d8d4d8d4d8d8d8d8d4d8d4d8d4d8d8<a8>c8<f4f4f8a8a+4a+4a+8>d8<a4a4a8g8a8a4r8a8>c8<f4f4a+8a+8a4a4>c8c8<a4a4a8g8f4r4a8>c8<f4f4a8a8a+4a+4>d8d8d4d4f8e8f8d4r8d8e8<a+4a+4a+4>f8d4r8d8f8<a4a4>d8<b8a4a8r8>a8>c8<f4f4f8a8a+4a+4a+8>d8<a4a4a8g8a8a8a16r8r16a8>c8<f4f4a+8a+8a4a4>c8c8c4c4<a8>c8<f4r4a8>c8<f4f4a8a8a+4a+4>d8d8d4d4f8e8f8d4r8d8e8<a+4a+4a+4>f8d4r8d8f8<a4a4>d8c+8<a4a4a4>c4f8f8<a+4>d8f8r4<a8a8a8r2r8>d8r4r8<a+8a+8a+8r2r8c+8c+8c+16r16<g4g16r16a4a16r8r16>f8g8d8d16r16d8d16r16d8d16r16d8d8r2c8c16r16c8c16r16c8c16r16c8c8r2d8d16r16d8d16r16d8d16r16d8d8r2c+8c+16r16c+8c+16r16<a8a16r16f8f16r4r16>d8e8<a4a8a16r16>g8a8c8c16r16c8c16r16c8c16r16<a8a16r16a8a16r16a8a16r16>c8c16r4r16f8g8c8c16r4r16g8f8c+8c+16r16c+8c+16r16c+8c+16r16<f8f16r4r16>e8c8<f8r4r8>>d8e8<a8a16r4r16>e8f8c8c16r16c8c16r16c8c16r16f8f16r16c8c16r16c8c16r16<f8f16r4r16>d8e8<a8a16r16a8a16r16>d8d16r16<a+8a+16r16a+8a+16r16a+8a+16r16a8a16r4r16>g8e8<a8a16r4r16>e8c+8d8d16r2r16d8d16r2r16c8c16r16c8c16r16c8c16r16c8g8r2<a+8a+16r2r16a8a16r2r16a8a16r16a8a16r16a8a16r16f4f16r16>d8e8f8d4d16r16d8e8f8d4d16r16d8e8f8c8c16r16c8c16r16f8f16r16c8g8r2<a+8a+16r2r16a8a16r2r16a8a16r16a8a16r16a8a16r16f4f16r4r8r16d2d4d8d16r1r4r16"
    ]

    #Gravity false
    melodies = [
        "r1r1r1r1r1r1r1r1r1r1r1r1r4r192f4f4f8f16f32f64f96a4a192a4g4f8f16f32f64f96r4r192a4a4a8a16a32a64a96r1r4r192f4f4f8f16f32f64f96a4a192a4g4f8f16f32f64f96r4r192a4a4a8a16a32a64a96r4r192>c+4c+4c+8c+16c+32c+64c+96r4r192<f4f4f8f16f32f64f96a4a192a4g4f8f16f32f64f96r4r192a+4a+4a+8a+16a+32a+64a+96g4g192r4>c4r8r16r32r64r96<a4a192r4>c+4r2f8r2r16r32r64r96d16d32d64r2r32r64r96",
        "r8r96d8d192r16r32r64r192d8d192r16r32r64r96d8d192r16r32r64r192d8d192r8r192c8c192r16r32r64r192c8c192r16r32r64r96c8c192r16r32r64r192c8c192r8r192c+8c+192r16r32r64r192c+8c+192r16r32r64r96c+8c+192r16r32r64r192c+8c+192r8r192c+8c+192r16r32r64r192c+8c+192r16r32r64r96c+8c+192r8r16r32r64r192d2d4d192e8e16e32e64e96f1a4a8a192g4g8a8a16a32a64a96r1d2d4d192e8e16e32e64e96f2f192e4e8e16e32e64e96g2g192a4a8a16a32a64a96g2g192f4f8f16f32f64f96r4r192d4d4d8d16d32d64d96d4d192d4d4d8d16d32d64d96r4r192f4f4f8f16f32f64f96g4g192a4g4f8f16f32f64f96r4r192d4d4d8d16d32d64d96d4d192d4d4d8d16d32d64d96r4r192e4e4e8e16e32e64e96r4r192a4a4a8a16a32a64a96r4r192d4d4d8d16d32d64d96d4d192d4d4d8d16d32d64d96r4r192f4f4f8f16f32f64f96e4e192r4g4r8r16r32r64r96e4e192r4a4r8r16r32r64r96>f8f96d8d192r16r32r64r192d8d192r16r32r64r96c+8c+192r16r32r64r192c+8c+192r2>>d16d32d192r16",
        "f8f64r16r32r64r192<a8a192r16r32r64r96>f8f192r16r32r64r96<a8a192r16r32r64r192>f8f64r16r32r64r192<a8a192r16r32r64r96>f8f192r16r32r64r96<a8a192r16r32r64r192>e8e64r16r32r64r192<a8a192r16r32r64r96>e8e192r16r32r64r96<a8a192r16r32r64r192>e8e64r16r32r64r192<a8a192r16r32r64r96>e8e192r16r32r64r96e32e64e96r192c+16c+32c+64c+96c+32c+64c+96r192<a2a4a192a8a16a32a64a96a1>c4c8c192c4c8c8c16c32c64c96c1<a+2a+4a+192a+8a+16a+32a+64a+96a+2a+192a+4a+8a+16a+32a+64a+96>c2c192c4c8c16c32c64c96c+2c+192c+4c+8c+16c+32c+64c+96r4r192<a4a4a8a16a32a64a96a4a192a4a4a8a16a32a64a96r4r192>c4c4c8c16c32c64c96c4c192c4c4c8c16c32c64c96r4r192<a+4a+4a+8a+16a+32a+64a+96a+4a+192a+4a+4a+8a+16a+32a+64a+96r4r192>c4c4c8c16c32c64c96r4r192e4e4e8e16e32e64e96r4r192<a4a4a8a16a32a64a96a4a192a4a4a8a16a32a64a96r4r192>d4d4d8d16d32d64d96c4c192r4e4r8r16r32r64r96c+4c+192r4e4r8r16r32r64r96a8a64r16r32r64r192a8a192r16r32r64r96a8a192r16r32r64r96>e8e192r16r32r64r192<a16a32a64r4r8r64r192>>d16d32d192r16"
    ]


    # NYAN
    melodies = [
        "f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+4r4<b4r4>c+4r4f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+2<b4r4b4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b4r4a+4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b2>c+2f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+4r4<b4r4>c+4r4f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+2<b4r4b4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b4r4a+4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b2>c+2<<e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2>>d+4e4f+2b2d+4e4f+4b4>c+4d+4c+4<a+4b2f+2d+4e4f+2b4>c+2<a+4b4>c+4e4d+4e4c+4",
        "f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+4r4<b4r4>c+4r4f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+2<b4r4b4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b4r4a+4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b2>c+2f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+4r4<b4r4>c+4r4f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+2<b4r4b4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b4r4a+4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b2>c+2<<e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2>>d+4e4f+2b2d+4e4f+4b4>c+4d+4c+4<a+4b2f+2d+4e4f+2b4>c+2<a+4b4>c+4e4d+4e4c+4",
        "f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+4r4<b4r4>c+4r4f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+2<b4r4b4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b4r4a+4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b2>c+2f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+4r4<b4r4>c+4r4f+2g+4r4c+4d+2<b8r8>d4c+4<b4r4b4r4>c+2d4r4d8r8c+8r8<b4>c+4d+4f+4g+4d+4f+4c+4d4<b4>c+4<b4>d+2f+4r4g+4d+4f+4c+4d4<b4>c+4d+4d4c+4<b4>c+4d4r4<b4>c+4d4f+4c+4d4c+4<b4>c+2<b4r4b4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b4r4a+4r4b4r4f+4g+4b4r4f+4g+4b4>c+4d+4c+4e4d+4e4f+4<b4r4b4r4f+4g+4b4g+4>e4d+4c+4<b4f+4d+4e4f+4b4r4f+4g+4b4r4f+4g+4b4b4>c+4d+4<b4f+4g+4f+4b2b4a+4b4f+4g+4b4>e4d+4e4f+4<b2>c+2<<e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2>e2<f+2>f+2<d+2>d+2<g+2>g+2<c+2>c+2<f+2>f+2<<b2>b2<b2>b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2e2g+2b2>e2<d+2f+2b2>d+2<c+2e2g+2b2<b2>d+2f+2b2>>d+4e4f+2b2d+4e4f+4b4>c+4d+4c+4<a+4b2f+2d+4e4f+2b4>c+2<a+4b4>c+4e4d+4e4c+4",
    ]


    # Komarovo
    melodies = [
        "a32r64r96a32r32r192a16a32a192r64r96a32a192r16r64r192a+16a+32r32a32a96r64r96>c8c32c192r64r192<a+16a+192r8r32r64r96a+32a+192r32a32a96r64r96g16g32g192r64r96g32g96r16r64f16f32f192r64r96g32g96r64r96a+8a+32r64r96a16a96r8r32r96a32r32a32a192r32a8a64a192r32r64r192a32r32r96a+16a+64a+96r32r192a16r32r64r96>c16c32c64r64r192<a+32a+64a+96r8r32r64r96a32r32a+32r32r192a8a64r32r96g32r32r192g16g64g96r64r192f8r4r8r96a32a96r64r192a32a96r64r192a16a32a96r64r96a16a96r32r192a+16a+32a+192r32a32a96r64>c8c32c64c96r64<a+16r8r32r64a+32a+192r32a32a96r64r96g8g96r32r64g32g192r32f16f32f64r64r192g32g96r64r192a+8a+32r64r192a16a64a192r8r32r96f32r32f32r32r192f16f32f64r96f16f192r16e16e32e96r64f32r32a8a16r64g16g32g192r8r96g64g96r32r96g64g96r32r96a8r16r32r64r96f16f32f96r64r192e32e64r64r192d16d64r8r16r32r96>d16d32d64r64r192e32e64r64d8d32d64r64c16r2r32r64r192e32e96r16r64r96e32e192r64r96e8e32e64e192r64f16r2r32r64r96f16f192r16g32g64r64f8f32f64f192r192e16e64r2r32r64e16e192r32r64r192f32f96r64r192e8e32e64e192r64d16r2r32r64r96d32d64r16r64r96e32e192r64r96d8d32d96r96c16c32r4r8r32r64e32e96r16r64e32e96r16r64r192e32e192r16r64r96e16e32e64e192r64f16r2r32r64r96f32f96r16r32f32f192r16r64f8r96e16e96r2r32r192<a16a32a64r64>c+16c+64c+96r32r96d8d16d32d64d192r2r8r96<a32a96r64r192a32a96r64r96a16a32a192r32a32a192r16r64a+16a+32a+96r64r192a32a96r64r192>c8c32r64<a+32a+64a+192r8r16r64r96a+32a+192r64r96a32a96r96g16g32g64g192r64r192g32g96r16r64r192f16f32f96r64g32g192r64r96a+8a+32r64r192a32a64a96r8r16r96a32r32a32r32a16a32r32a32a192r16r64a+16a+32a+64a+192r64r192a32a192r64r96>c8c32c96r64r192<a+32a+64a+192r8r16r64r96a32a192r64r192a+32r32a16a32a64a96r96g32g96r16r96g16g32g64r64r192f16f32f96r64r192>d8d16d32r8r32r192<a64a96r32a64a96r32r96a16a32a96r16r64a32a192r32r192a+16a+64a+192r32a32a64r32>c8c32r64r192<a+32a+64r8r32r64r96a+32a+192r32a32a96r64r192g16g32g96r64r96g32g64g192r16r192f16f32r32g32g96r64r96a+8a+64a+192r64a16a64a192r8r32r64r96f32r32f32r32r192f16f32f64f96r32r64r96f32f96r32e16e32e64r64f32f96r32a8a32r64r192g16g192r8r32r64r96g64g192r32r192g32r64r96a64a192r192a16a32a64a96r32r192g16g192r16r32r64r96f32f64f96r32e32e64e192r96d16d64r8r32r96>d16d32d64r32e32e192r64r96d8d32d96r64c32c64c192r2r32r64r96e32e96r16r64r96e32r32e8e32e64r96f16f96r2r32r64r96f16f32r32g32g192r64r96f8f32f64r96e16e192r2r16e32e64e192r16r64r192f32f192r64r96e8e32e192r64r192d16r2r16d16d32d96r64r192e32e64r64d8d32d64d192r64c32c64r4r8r16r96e16e32r64r96e32r16r32r192e32r16r64r96e16e32e64e192r64f32f64f96r2r16r192f16f32f192r64r96g32g192r16r64r96f8r96e16r2r32r96<a16a32a64a96r64>c+16c+32c+64r64d8d16d32d64r2r8r96<a32r64r96a32r32r64a16a32a192r32a32a192r16r64a+16a+32a+96r64r192a32a96r64r192>c8c32r64<a+32a+64a+192r8r16r64r96a+32a+96r64r192a32a96r96g16g32g64g192r64r192g32g96r16r64r192f16f32f96r64g32g192r64r96a+8a+32r64r192a32a64a96r8r16r96a32r32a32r32a16a32r32a32a192r16r64a+16a+32a+64a+192r64r192a32a192r64r96>c8c32c96r64r192<a+32a+64a+192r8r16r64r96a32a192r64r192a+32r32a16a32a64a96r96g32g64r16r192g16g32g64r64r192f16f32f64r64>d8d16d32r8r32r192<a64a96r32a64a96r32r96a8a64a96r64r192a32a96r32a+16a+32a+64a+192r96a16a192r32r64>c8r64<a+16r8r32r64r96a+32r64r192a32a64r64r192g8g64g96r32g32g96r64r192f16f32f64f192r64r192g32g96r64r192a+8a+32r64r192a32a64a96r8r16r192f32f192r32f32f192r64r96f16f32f64f96r16r192f32f192r32e16e32e64r64f32f96r64r96a8a32a64r64r192g16g96r8r32a+32r32a+64a+96r32a64r192a16a32a192r64g32g192r16r64r192e16e32e64e96r96f16f32f96r64r192d16d64r8r32r96>d16d32d64d96r64r192e32e192r64r192d8d32d96r64c32c64c96r2r16e32e96r16r64r192e32e192r32e8e32e192r64f16f96r2r16r192f16f32r32g32r64r192f8f32f64f192r96e32e64e96r2r16r96e32e64r16r64f32f64r64r192e8e32e96r64r192d32d64d192r2r16r192d32d64d192r16r96e32e96r64r192d8d16d192r192c16r4r8r32r64r192e16e32e64r64e32e96r16r64r192e32e192r16r64r96e16e32e64e192r64f16r2r32r64r96f16f32f96r64r192g32g64r16r64f16f32f64f192r64e32e64e192r2r16r192<a16a32a64a192r64>c+16c+32c+192r64r96d8d16d32d64d96r4r8r16r32r64r96d16d32d96r32e32r64r192d8d32d96r64r192c16r2r16e32e96r16r64r192e32e192r64r96e8e32e192r64f16r2r16r96f16f32r32r192g32g192r64r96f8f32f96r64e32e64e96r2r16r96e16e32e96r64r96f32f96r64r192e8e32e64r64d32d96r2r16r192d16d32d64r64r192e16e32e64e96r96d16d32d64d192r64c32c64c96r4r8r32r64r96e32e192r16r64r192e16e32e96r64r96e16e32e96r96e8r96f32f64f192r2r16r64f16f32f192r32g16g32r64r96f16f32f64f96r64r192e32e64r2r32r64r96<a16a32a96r64r192>c+16c+32c+64r64r192d4d8d16d32d64d96r8r96",
        "a32r64r96a32r32r192a16a32a192r64r96a32a192r16r64r192a+16a+32r32a32a96r64r96>c8c32c192r64r192<a+16a+192r8r32r64r96a+32a+192r32a32a96r64r96g16g32g192r64r96g32g96r16r64f16f32f192r64r96g32g96r64r96a+8a+32r64r96a16a96r8r32r96a32r32a32a192r32a8a64a192r32r64r192a32r32r96a+16a+64a+96r32r192a16r32r64r96>c16c32c64r64r192<a+32a+64a+96r8r32r64r96a32r32a+32r32r192a8a64r32r96g32r32r192g16g64g96r64r192f8r4r8r96a32a96r64r192a32a96r64r192a16a32a96r64r96a16a96r32r192a+16a+32a+192r32a32a96r64>c8c32c64c96r64<a+16r8r32r64a+32a+192r32a32a96r64r96g8g96r32r64g32g192r32f16f32f64r64r192g32g96r64r192a+8a+32r64r192a16a64a192r8r32r96f32r32f32r32r192f16f32f64r96f16f192r16e16e32e96r64f32r32a8a16r64g16g32g192r8r96g64g96r32r96g64g96r32r96a8r16r32r64r96f16f32f96r64r192e32e64r64r192d16d64r8r16r32r96>d16d32d64r64r192e32e64r64d8d32d64r64c16r2r32r64r192e32e96r16r64r96e32e192r64r96e8e32e64e192r64f16r2r32r64r96f16f192r16g32g64r64f8f32f64f192r192e16e64r2r32r64e16e192r32r64r192f32f96r64r192e8e32e64e192r64d16r2r32r64r96d32d64r16r64r96e32e192r64r96d8d32d96r96c16c32r4r8r32r64e32e96r16r64e32e96r16r64r192e32e192r16r64r96e16e32e64e192r64f16r2r32r64r96f32f96r16r32f32f192r16r64f8r96e16e96r2r32r192<a16a32a64r64>c+16c+64c+96r32r96d8d16d32d64d192r2r8r96<a32a96r64r192a32a96r64r96a16a32a192r32a32a192r16r64a+16a+32a+96r64r192a32a96r64r192>c8c32r64<a+32a+64a+192r8r16r64r96a+32a+192r64r96a32a96r96g16g32g64g192r64r192g32g96r16r64r192f16f32f96r64g32g192r64r96a+8a+32r64r192a32a64a96r8r16r96a32r32a32r32a16a32r32a32a192r16r64a+16a+32a+64a+192r64r192a32a192r64r96>c8c32c96r64r192<a+32a+64a+192r8r16r64r96a32a192r64r192a+32r32a16a32a64a96r96g32g96r16r96g16g32g64r64r192f16f32f96r64r192>d8d16d32r8r32r192<a64a96r32a64a96r32r96a16a32a96r16r64a32a192r32r192a+16a+64a+192r32a32a64r32>c8c32r64r192<a+32a+64r8r32r64r96a+32a+192r32a32a96r64r192g16g32g96r64r96g32g64g192r16r192f16f32r32g32g96r64r96a+8a+64a+192r64a16a64a192r8r32r64r96f32r32f32r32r192f16f32f64f96r32r64r96f32f96r32e16e32e64r64f32f96r32a8a32r64r192g16g192r8r32r64r96g64g192r32r192g32r64r96a64a192r192a16a32a64a96r32r192g16g192r16r32r64r96f32f64f96r32e32e64e192r96d16d64r8r32r96>d16d32d64r32e32e192r64r96d8d32d96r64c32c64c192r2r32r64r96e32e96r16r64r96e32r32e8e32e64r96f16f96r2r32r64r96f16f32r32g32g192r64r96f8f32f64r96e16e192r2r16e32e64e192r16r64r192f32f192r64r96e8e32e192r64r192d16r2r16d16d32d96r64r192e32e64r64d8d32d64d192r64c32c64r4r8r16r96e16e32r64r96e32r16r32r192e32r16r64r96e16e32e64e192r64f32f64f96r2r16r192f16f32f192r64r96g32g192r16r64r96f8r96e16r2r32r96<a16a32a64a96r64>c+16c+32c+64r64d8d16d32d64r2r8r96<a32r64r96a32r32r64a16a32a192r32a32a192r16r64a+16a+32a+96r64r192a32a96r64r192>c8c32r64<a+32a+64a+192r8r16r64r96a+32a+96r64r192a32a96r96g16g32g64g192r64r192g32g96r16r64r192f16f32f96r64g32g192r64r96a+8a+32r64r192a32a64a96r8r16r96a32r32a32r32a16a32r32a32a192r16r64a+16a+32a+64a+192r64r192a32a192r64r96>c8c32c96r64r192<a+32a+64a+192r8r16r64r96a32a192r64r192a+32r32a16a32a64a96r96g32g64r16r192g16g32g64r64r192f16f32f64r64>d8d16d32r8r32r192<a64a96r32a64a96r32r96a8a64a96r64r192a32a96r32a+16a+32a+64a+192r96a16a192r32r64>c8r64<a+16r8r32r64r96a+32r64r192a32a64r64r192g8g64g96r32g32g96r64r192f16f32f64f192r64r192g32g96r64r192a+8a+32r64r192a32a64a96r8r16r192f32f192r32f32f192r64r96f16f32f64f96r16r192f32f192r32e16e32e64r64f32f96r64r96a8a32a64r64r192g16g96r8r32a+32r32a+64a+96r32a64r192a16a32a192r64g32g192r16r64r192e16e32e64e96r96f16f32f96r64r192d16d64r8r32r96>d16d32d64d96r64r192e32e192r64r192d8d32d96r64c32c64c96r2r16e32e96r16r64r192e32e192r32e8e32e192r64f16f96r2r16r192f16f32r32g32r64r192f8f32f64f192r96e32e64e96r2r16r96e32e64r16r64f32f64r64r192e8e32e96r64r192d32d64d192r2r16r192d32d64d192r16r96e32e96r64r192d8d16d192r192c16r4r8r32r64r192e16e32e64r64e32e96r16r64r192e32e192r16r64r96e16e32e64e192r64f16r2r32r64r96f16f32f96r64r192g32g64r16r64f16f32f64f192r64e32e64e192r2r16r192<a16a32a64a192r64>c+16c+32c+192r64r96d8d16d32d64d96r4r8r16r32r64r96d16d32d96r32e32r64r192d8d32d96r64r192c16r2r16e32e96r16r64r192e32e192r64r96e8e32e192r64f16r2r16r96f16f32r32r192g32g192r64r96f8f32f96r64e32e64e96r2r16r96e16e32e96r64r96f32f96r64r192e8e32e64r64d32d96r2r16r192d16d32d64r64r192e16e32e64e96r96d16d32d64d192r64c32c64c96r4r8r32r64r96e32e192r16r64r192e16e32e96r64r96e16e32e96r96e8r96f32f64f192r2r16r64f16f32f192r32g16g32r64r96f16f32f64f96r64r192e32e64r2r32r64r96<a16a32a96r64r192>c+16c+32c+64r64r192d4d8d16d32d64d96r8r96",
        "a32r64r96a32r32r192a16a32a192r64r96a32a192r16r64r192a+16a+32r32a32a96r64r96>c8c32c192r64r192<a+16a+192r8r32r64r96a+32a+192r32a32a96r64r96g16g32g192r64r96g32g96r16r64f16f32f192r64r96g32g96r64r96a+8a+32r64r96a16a96r8r32r96a32r32a32a192r32a8a64a192r32r64r192a32r32r96a+16a+64a+96r32r192a16r32r64r96>c16c32c64r64r192<a+32a+64a+96r8r32r64r96a32r32a+32r32r192a8a64r32r96g32r32r192g16g64g96r64r192f8r4r8r96a32a96r64r192a32a96r64r192a16a32a96r64r96a16a96r32r192a+16a+32a+192r32a32a96r64>c8c32c64c96r64<a+16r8r32r64a+32a+192r32a32a96r64r96g8g96r32r64g32g192r32f16f32f64r64r192g32g96r64r192a+8a+32r64r192a16a64a192r8r32r96f32r32f32r32r192f16f32f64r96f16f192r16e16e32e96r64f32r32a8a16r64g16g32g192r8r96g64g96r32r96g64g96r32r96a8r16r32r64r96f16f32f96r64r192e32e64r64r192d16d64r8r16r32r96>d16d32d64r64r192e32e64r64d8d32d64r64c16r2r32r64r192e32e96r16r64r96e32e192r64r96e8e32e64e192r64f16r2r32r64r96f16f192r16g32g64r64f8f32f64f192r192e16e64r2r32r64e16e192r32r64r192f32f96r64r192e8e32e64e192r64d16r2r32r64r96d32d64r16r64r96e32e192r64r96d8d32d96r96c16c32r4r8r32r64e32e96r16r64e32e96r16r64r192e32e192r16r64r96e16e32e64e192r64f16r2r32r64r96f32f96r16r32f32f192r16r64f8r96e16e96r2r32r192<a16a32a64r64>c+16c+64c+96r32r96d8d16d32d64d192r2r8r96<a32a96r64r192a32a96r64r96a16a32a192r32a32a192r16r64a+16a+32a+96r64r192a32a96r64r192>c8c32r64<a+32a+64a+192r8r16r64r96a+32a+192r64r96a32a96r96g16g32g64g192r64r192g32g96r16r64r192f16f32f96r64g32g192r64r96a+8a+32r64r192a32a64a96r8r16r96a32r32a32r32a16a32r32a32a192r16r64a+16a+32a+64a+192r64r192a32a192r64r96>c8c32c96r64r192<a+32a+64a+192r8r16r64r96a32a192r64r192a+32r32a16a32a64a96r96g32g96r16r96g16g32g64r64r192f16f32f96r64r192>d8d16d32r8r32r192<a64a96r32a64a96r32r96a16a32a96r16r64a32a192r32r192a+16a+64a+192r32a32a64r32>c8c32r64r192<a+32a+64r8r32r64r96a+32a+192r32a32a96r64r192g16g32g96r64r96g32g64g192r16r192f16f32r32g32g96r64r96a+8a+64a+192r64a16a64a192r8r32r64r96f32r32f32r32r192f16f32f64f96r32r64r96f32f96r32e16e32e64r64f32f96r32a8a32r64r192g16g192r8r32r64r96g64g192r32r192g32r64r96a64a192r192a16a32a64a96r32r192g16g192r16r32r64r96f32f64f96r32e32e64e192r96d16d64r8r32r96>d16d32d64r32e32e192r64r96d8d32d96r64c32c64c192r2r32r64r96e32e96r16r64r96e32r32e8e32e64r96f16f96r2r32r64r96f16f32r32g32g192r64r96f8f32f64r96e16e192r2r16e32e64e192r16r64r192f32f192r64r96e8e32e192r64r192d16r2r16d16d32d96r64r192e32e64r64d8d32d64d192r64c32c64r4r8r16r96e16e32r64r96e32r16r32r192e32r16r64r96e16e32e64e192r64f32f64f96r2r16r192f16f32f192r64r96g32g192r16r64r96f8r96e16r2r32r96<a16a32a64a96r64>c+16c+32c+64r64d8d16d32d64r2r8r96<a32r64r96a32r32r64a16a32a192r32a32a192r16r64a+16a+32a+96r64r192a32a96r64r192>c8c32r64<a+32a+64a+192r8r16r64r96a+32a+96r64r192a32a96r96g16g32g64g192r64r192g32g96r16r64r192f16f32f96r64g32g192r64r96a+8a+32r64r192a32a64a96r8r16r96a32r32a32r32a16a32r32a32a192r16r64a+16a+32a+64a+192r64r192a32a192r64r96>c8c32c96r64r192<a+32a+64a+192r8r16r64r96a32a192r64r192a+32r32a16a32a64a96r96g32g64r16r192g16g32g64r64r192f16f32f64r64>d8d16d32r8r32r192<a64a96r32a64a96r32r96a8a64a96r64r192a32a96r32a+16a+32a+64a+192r96a16a192r32r64>c8r64<a+16r8r32r64r96a+32r64r192a32a64r64r192g8g64g96r32g32g96r64r192f16f32f64f192r64r192g32g96r64r192a+8a+32r64r192a32a64a96r8r16r192f32f192r32f32f192r64r96f16f32f64f96r16r192f32f192r32e16e32e64r64f32f96r64r96a8a32a64r64r192g16g96r8r32a+32r32a+64a+96r32a64r192a16a32a192r64g32g192r16r64r192e16e32e64e96r96f16f32f96r64r192d16d64r8r32r96>d16d32d64d96r64r192e32e192r64r192d8d32d96r64c32c64c96r2r16e32e96r16r64r192e32e192r32e8e32e192r64f16f96r2r16r192f16f32r32g32r64r192f8f32f64f192r96e32e64e96r2r16r96e32e64r16r64f32f64r64r192e8e32e96r64r192d32d64d192r2r16r192d32d64d192r16r96e32e96r64r192d8d16d192r192c16r4r8r32r64r192e16e32e64r64e32e96r16r64r192e32e192r16r64r96e16e32e64e192r64f16r2r32r64r96f16f32f96r64r192g32g64r16r64f16f32f64f192r64e32e64e192r2r16r192<a16a32a64a192r64>c+16c+32c+192r64r96d8d16d32d64d96r4r8r16r32r64r96d16d32d96r32e32r64r192d8d32d96r64r192c16r2r16e32e96r16r64r192e32e192r64r96e8e32e192r64f16r2r16r96f16f32r32r192g32g192r64r96f8f32f96r64e32e64e96r2r16r96e16e32e96r64r96f32f96r64r192e8e32e64r64d32d96r2r16r192d16d32d64r64r192e16e32e64e96r96d16d32d64d192r64c32c64c96r4r8r32r64r96e32e192r16r64r192e16e32e96r64r96e16e32e96r96e8r96f32f64f192r2r16r64f16f32f192r32g16g32r64r96f16f32f64f96r64r192e32e64r2r32r64r96<a16a32a96r64r192>c+16c+32c+64r64r192d4d8d16d32d64d96r8r96",
    ]
'''