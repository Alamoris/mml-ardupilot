import sys
import getopt
import mido
import pandas as pd
import numpy as np


def main(argv):
    try:
        opts, args = getopt.getopt(argv, "hi:o:p:b:", ["help", "input=", "output=", "readable-midi", "group-by="])
    except getopt.GetoptError as err:
        print(err)
        usage()
        sys.exit(2)
    input = ""
    output = ""
    midi_to_text = False
    ppq = 48
    group_by = "instrument"
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-i", "--input"):
            input = a
        elif o in ("-o", "--output"):
            output = a
        elif o in ("-p", "--ppq"):
            ppq = int(a)
        elif o in ("--readable-midi"):
            midi_to_text = True
        elif o in ("-g", "--group-by"):
            group_by = a
        else:
            assert False, "unhandled option"
    if input.endswith(".midi") or input.endswith(".mid"):
        (channels, names, tempo, PPQ) = read_midi(input, midi_to_text)
        channels, names, leftovers = prepare_midi_channels(channels, names)
        print('channels', len(channels))
        channels = channel_length(channels, PPQ)
        cmds = channel_to_mml(channels, names, ppq)
        with open(output, "w") as f:
            f.write(header())
            f.write("; Tempo\n")
            BPM_min = 60e6/np.min(tempo['tempo'])
            BPM_max = 60e6/np.max(tempo['tempo'])
            if BPM_min == BPM_max:
                f.write(f"; BPM = {BPM_max}\n")
            else:
                f.write(f"; BPM_min = {BPM_min}\n")
                f.write(f"; BPM_max = {BPM_max}\n")
            f.write(f"t{int(0.4096*60e6/np.max(tempo['tempo']))}\n")
            f.write("\n")
            f.write(";************************\n")
            for line in cmds:
                f.write(line)
    elif input.endswith(".txt") or input.endswith(".mml"):
        channels = read_mml(input)
        cmd_table = commands_to_table(channels)
        table_to_midi(cmd_table, output, by=group_by)


# Everyone needs help from time to time. If arguments or options are
# no longer present, this method prints the help in the console
def usage():
    print("usage: python midi2mml.py -i <input> -o <output> [--readable-midi --group-by <instrument|channel>]")
    print("")
    print("       <input>  is the MIDI, which acts as input file. The file specified here")
    print("                will be converted to mml format. If the file contains blanks, it")
    print("                must be put in quotation marks.")
    print("")
    print("      <output>  the name of the output file. into this file the converted midi is")
    print("                written. If the file contains blanks,it must be put in quotation")
    print("                marks.")
    print("")
    print(" MIDI 2 MML only")
    print("")
    print(" readable-midi  optional argument. when set, each midi channel is written to a")
    print("                separate text file in a human readable format. The text files have")
    print("                the name channel_<N>.txt where <N> is the channel number. Please")
    print("                note that the channel number of the midi does not have to match")
    print("                the channel number of the mml, because the midi has additional")
    print("                information and control channels, which do not exist in mml.")
    print("")
    print(" MML 2 MIDI only")
    print("")
    print("      group-by  May be \"instrument\" or \"channel\". In an MML there can be several")
    print("                instruments in one channel, in a midi one instrument per channel is")
    print("                defined. Most of the time it is useful to sort MIDIs by instrument.")
    print("                But from un on (e.g. drums) it is also helpful to sort by channel.")
    


# This method creates a standard header in which, if desired, author,
# title, origin and a comment can be written.
def header(author="", title="", game="", comment=""):
    lines  = "#amk 2\n"
    lines += ";************************\n"
    lines += "\n"
    lines += "; SPC Generator Info\n"
    lines += "#SPC\n"
    lines += "{\n"
    lines += f"    #author  \"{author}\"\n"
    lines += f"    #title   \"{title}\"\n"
    lines += f"    #game    \"{game}\"\n"
    lines += f"    #comment \"{comment}\"\n"
    lines += "}\n"
    lines += ";************************\n"
    lines += "\n"
    return lines


# In MIDI files the pitch of a note is given as a key number on the
# claviature. The smallest key - 1 - corresponds to a C0. The key C5
# corresponds to number 61. This function determines the pitch and
# octave from the key number.
def key_to_pitch(number):
    if number == "r":
        return (np.nan, "r")
    octave = int(number/12)
    note = int(np.mod(number,12))
    return (octave, list(["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"])[note])


# the reversed version of key_to_pitch.
def pitch_to_key(note, octave=5):
    key = {
        "c" : 0,
        "d" : 2,
        "e" : 4,
        "f" : 5,
        "g" : 7,
        "a" : 9,
        "b" : 11,
    }[note[0]]
    if len(note)>1:
        if note[1]=="+":
            key += 1
    key += 12*octave
    return key


# In MIDI files the length is given in ticks. However, MML allows you
# to specify the notes in classic note value notation for better
# readability. For the conversion of ticks into note values the PPQ
# (parts per quarter note) must be specified, which is stored in the
# MIDI. PPQ ticks correspond exactly to a quarter note, 4*PPQ ticks
# correspond to a whole note. The PPQ value can be multiples of 24, up
# to a maximum of 960.
def ticks_to_value(ticks, PPQ):
    ticks_per_note = np.array([])
    ticks_tri = np.array([])
    for i in np.arange(int(4*PPQ), 0, -1):
        if np.mod(4*PPQ, i) == 0:
            if np.mod(i, 3) == 0:
                ticks_tri = np.append(ticks_tri, [i])
            else:
                ticks_per_note = np.append(ticks_per_note, [i])
    ticks_per_note = np.append(ticks_tri, ticks_per_note)
    val = ""
    for tpn in ticks_per_note:
        factor = int(ticks/tpn)
        if factor > 0:
            if len(val) == 0:
                val += f"{int(4*PPQ/tpn)}"
                val += f"^{int(4*PPQ/tpn)}"*(factor-1)
                print(f'val: {val}/factor {factor}/tpn {tpn}|{ticks}')
            else:
                val += f"^{int(4*PPQ/tpn)}"*factor
        ticks = np.mod(ticks, tpn)
    # dotted notes for better readability
    # for i in range(8):
    #     expr = f"{2**i}"
    #     for j in range(i, 8):
    #         expr += f"^{2**(j+1)}"
    #         subst = f"{2**i}" + "."*(j-i+1)
    #         if val == expr:
    #             return subst
    return val


# the reversed version of ticks_to_value.
def value_to_ticks(value, PPQ=48):
    # get rid of dottet notes
    while "." in value:
        idx = value.find(".")
        for i in range(idx):
            try:
                num = int(value[i:idx])
                break
            except ValueError:
                error = True
        value = value[0:idx] + "^" + str(2*num) + value[idx+1:len(value)]
    # convert note value in ticks
    ticks = 0
    for v in value.split("^"):
        if len(v) == 0:
            return 4*PPQ
        if v[0] == "=":
            ticks += int(v[1:len(v)])
        else:
            if int(v) == 0:
                return 4*PPQ
            else:
                ticks += 4*PPQ/int(v)
    return int(ticks)


# This Method is used to read the MIDI file. The individual channels
# are converted into DataFrames. The channels contain all instructions
# and their chronological execution. Since MIDI instructions are
# relative, an absolute time is generated afterwards, which
# facilitates later processing. The name of the channels is written to
# the list names. Tempo and PPQ (Parts per Quarter) are also extracted
# individually.
def read_midi(filename, midi_to_text=False, target_PPQ=48):
    midi = mido.MidiFile(filename)
    PPQ = midi.ticks_per_beat
    print('PPQ', PPQ)
    channels = list()
    names = list()
    tempo = pd.DataFrame()

    track_id = 0
    for i, track in enumerate(midi.tracks):
        if track_id >= 2:
            break
        track_id += 1

        print(f"extract channel {i+1} of {len(midi.tracks)}")
        content = []
        df = pd.DataFrame()
        channelname = "NA"
        for msg in track:
            content += [str(msg)]
            if msg.type == "track_name":
                channelname = msg.name
            if msg.type == "note_on" or msg.type == "note_off":
                type = msg.type
                if msg.velocity == 0:
                    type = "note_off"
                tmp = pd.DataFrame({
                    "type":[type],
                    "channel":[msg.channel],
                    "note":[msg.note],
                    "velocity":[msg.velocity],
                    "ticks_delta":[msg.time]
                })
                df = pd.concat([df, tmp])
            if msg.type == "control_change":
                tmp = pd.DataFrame({
                    "type":[msg.type],
                    "channel":[msg.channel],
                    "control":[msg.control],
                    "value":[msg.value],
                    "ticks_delta":[msg.time]
                })
                df = pd.concat([df, tmp])
            if msg.type == "program_change":
                tmp = pd.DataFrame({
                    "type":[msg.type],
                    "channel":[msg.channel],
                    "ticks_delta":[msg.time]
                })
                df = pd.concat([df, tmp])
            if msg.type == "pitchwheel":
                tmp = pd.DataFrame({
                    "type":[msg.type],
                    "channel":[msg.channel],
                    "pitch":[msg.pitch],
                    "ticks_delta":[msg.time]
                })
                df = pd.concat([df, tmp])
            if msg.type == "set_tempo":
                tmp = pd.DataFrame({
                    "tempo":[msg.tempo],
                    "time":[msg.time],
                })
                tempo = pd.concat([tempo, tmp])
        if midi_to_text:
            with open(f"track_{i}", "w") as f:
                for line in content:
                    f.write(line+"\n")
        if "ticks_delta" not in df.columns:
            continue
        if "note_on" not in df["type"].values:
            continue
        df["ticks_abs"] = df["ticks_delta"].cumsum()
        df["ticks_abs"] = np.round(df["ticks_abs"]*target_PPQ/PPQ).astype(int)
        df["ticks_abs"] = df["ticks_abs"].astype(int)
        print(f"Note_min={df['note'].min()}")
        print(f"Note_max={df['note'].max()}")
        df["note"] = df["note"].fillna(0)
        df["note"] = np.round(df["note"]).astype(int)
        names += [channelname]
        channels += [df]
    return (channels, names, tempo, PPQ)


# For the actual conversion of MIDI commands into MML notation only
# the note_on and note_off commands are of interest. These commands
# are extracted with this method and written to a new list. This list
# can be longer than the original channel list, because MML does not
# allow multiple notes in one channel at the same time, so they have
# to be split up into several channels.
def prepare_midi_channels(channels, names):
    new_channels = list()
    new_names = list()
    for i, channel in enumerate(channels):
        print(f"prepare channel {i+1} of {len(channels)}")
        idx = np.logical_or(channel["type"]=="note_on", channel["type"]=="note_off")
        channel = channel[idx].reset_index(drop=True)
        retlist = list()
        retlist.append(extract_simultaneous_notes(channel, 0, retlist))
        new_channels = new_channels + retlist
        for x in range(len(retlist)):
            new_names.append([names[i]])
    return new_channels, new_names, 0


# If there are notes in a channel at the same time, only one of the
# notes played simultaneously will be extracted. The other(s) remain
# in the list. If the leftover list is not empty, another channel is
# iteratively added to the channel list retlist until this initial
# list is empty. If (for whatever reason) the list is never empty,
# there is a termination criterion, which intervenes at more than 99
# iteration depths and stops the extraction.
def extract_simultaneous_notes(channel, iteration, retlist):
    if iteration > 99:
        print("more than 99 iterations were performed, most likely there is an error in the file")
        return pd.DataFrame()
    idx_on = channel["type"]=="note_on"
    idx_off = channel["type"]=="note_off"
    if len(idx_on)==0 or len(idx_off)==0:
        return pd.DataFrame()
    pnt_on = -1
    pnt_off = -1
    extract = pd.DataFrame()
    leftover = channel.copy()
    t_prev = 0
    while True:
        # find next note_on even
        check = np.logical_and(idx_on, channel.index > pnt_on)
        if not max(check):
            break
        pnt_on = np.argmax(check)
        
        # find the corresponding note_off event
        note = channel.iloc[pnt_on].note
        
        check = np.logical_and(idx_off, np.logical_and(channel["note"]==note, channel.index > pnt_on))
        if not max(check):
            break
        pnt_off = np.argmax(check)
        
        note_length = channel.iloc[pnt_off].ticks_abs - channel.iloc[pnt_on].ticks_abs

        rest = channel.iloc[pnt_on].ticks_abs - t_prev
        if rest > 0:
            extract = pd.concat([extract, pd.DataFrame({"note":["r"], "ticks":[rest]})])
        extract = pd.concat([extract, pd.DataFrame({"note":[note], "ticks":[note_length]})])
        leftover = leftover.drop([pnt_off])
        leftover = leftover.drop([pnt_on])
        pnt_on = pnt_off
        t_prev = channel.iloc[pnt_off].ticks_abs
    leftover = leftover.reset_index(drop=True)
    if len(leftover) > 0:
        retlist.append(extract_simultaneous_notes(leftover, iteration+1, retlist))
    return extract


# Usually the individual tracks in a MIDI file do not have the same
# length. In an MML, however, the individual channels must end at the
# same time, otherwise it will not be looped correctly. This method
# first determines the longest channel, rounds it to the next full
# beat|tick|bar (argument round_to_next) and then adjusts all channels to this
# length by inserting a pause at the end.
def channel_length(channels, PPQ, round_to_next="beat"):
    length = np.array([])
    for channel in channels:
        length_i = np.sum(channel["ticks"])
        if round_to_next == "tick":
            length_i = int(length_i)
        if round_to_next == "beat":
            length_i = int(PPQ*np.ceil(length_i/PPQ))
        if round_to_next == "bar":
            length_i = int(4*PPQ*np.ceil(length_i/PPQ))
        length = np.append(length, [length_i])
    new_channels = list()
    for channel in channels:
        li = np.sum(channel["ticks"])
        if li < length.max():
            channel = pd.concat([channel, pd.DataFrame({"note":["r"], "ticks":[length.max()-li]})])
        new_channels.append(channel)
    return new_channels


# The actual conversion of MIDI to MML commands is done in this
# method. The channels are processed one after the other. For each
# channel, all notes from the MIDI are converted into an MML command
# with corresponding pitch and length.
def channel_to_mml(channels, names, PPQ):
    cmds = list()
    for i, channel in enumerate(channels):
        (octave_prev, note) = key_to_pitch(channel[channel["note"]!="r"].iloc[0].note)
        note_min = channel[channel["note"]!="r"]["note"].min()
        note_max = channel[channel["note"]!="r"]["note"].max()
        (octave_min, note) = key_to_pitch(note_min)
        (octave_max, note) = key_to_pitch(note_max)
        cmd = "\n"
        if i <= 7:
            cmd += f"; {names[i]}\n"
            cmd += f"#{i}\n"
            cmd += f"o{octave_prev}   ; +{octave_max-octave_prev} / -{octave_prev-octave_min}\n"
        else:
            cmd += f"; ; {names[i]}\n"
            cmd += f"; #{i}\n"
            cmd += f"; o{octave_prev}   ; +{octave_max-octave_prev} / -{octave_prev-octave_min}\n"
            cmd += "; "
        for j, row in channel.iterrows():
            (octave, note) = key_to_pitch(row.note)
            value = ticks_to_value(row.ticks, PPQ)

            if note != "r":
                octave_diff = octave-octave_prev
                if octave_diff > 0:
                    cmd += ">"*octave_diff  # + " "
                if octave_diff < 0:
                    cmd += "<"*-octave_diff  # + " "
                octave_prev = octave
            # cmd += f"{note}{value}"
            cmd += f"{note}{value.replace('^', note)}"
        cmd += "\n"
        cmds += [cmd]
    return cmds


# This method reads an MML (text file) and extracts the individual
# tracks #0 to #7.
def read_mml(infile):
    with open(infile, "r") as f:
        content = f.read()
    # remove comments
    while ";" in content:
        start = content.find(";")
        end = content.find("\n", start)
        content = content[0:start] + content[end+1:len(content)]
    # remove linebreaks
    content = content.replace("\n", "")
    # remove blanks
    content = content.replace(" ", "")
    # remove intro indicator
    content = content.replace("/", "")
    channels = []
    for i in range(1,9):
        start = content.find(f"#{i-1}")
        end = content.find(f"#{i}")
        if end < 1:
            end = len(content)
        channels += [content[start:end]]
    # expand (super) loops
    labeled_loop = dict()
    remote_code = dict()
    for i, channel in enumerate(channels):
        channel = expand_labeled_loops(channel, labeled_loop, remote_code)
        tmp = expand_loop(channel)
        channels[i] = split_commands(tmp)
    return channels


# This method finds labeled loops and remote code and expands
# them. This makes the channel longer, but easier to understand for
# the converter.
def expand_labeled_loops(channel, labeled_loop, remote_code):
    while "(" in channel:
        start = channel.find("(")
        end = channel.find(")", start)
        loop_num = channel[start+1:end]
        if channel[end+1] == "[":
            end2 = channel.find("]", end)
            # find loops in loops
            while channel[end2+1] == "]":
                end2 = channel.find("]", end2+2)
            loop_content = channel[end+2:end2]
            if "!" in loop_num:
                remote_code[loop_num] = loop_content
            else:
                labeled_loop[loop_num] = loop_content
            channel = channel[0:end+1]+channel[end2+1:len(channel)]
        else:
            for i in range(1, 5):
                try:
                    num = int(channel[end+1:end+1+i])
                except ValueError:
                    error = True
            if "!" in loop_num:
                replace = remote_code[loop_num]
            else:
                replace = labeled_loop[loop_num]
            channel = channel[0:start] + replace*num + channel[end+1:len(channel)]
    return channel


# MML supports loops to save storage space. As it is easier to convert
# single notes, without any other modifications all loops are expanded
# first.
def expand_loop(channel):
    while "[[" in channel:
        start = channel.find("[[")
        end = channel.find("]]", start)
        loop = channel[start+2:end]
        loop = loop.replace("[", "").replace("]", "")
        for i in range(5,0,-1):
            try:
                count = int(channel[end+2:end+2+i])
                break
            except ValueError:
                count = 1
        channel = channel[0:start] + loop*count  + channel[end+2+i:-1]
    while "[" in channel:
        start = channel.find("[")
        end = channel.find("]", start)
        loop = channel[start+1:end]
        for i in range(5,0,-1):
            try:
                count = int(channel[end+1:end+1+i])
                break
            except ValueError:
                count = 1
        channel = channel[0:start] + loop*count  + channel[end+1+i:-1]
    return channel


# The single mml commands do not need separators to be distinguished
# from each other. This method splits the channel, which is a single
# continuous string, into single commands for better processing.
def split_commands(channel):
    i = 0
    while i < len(channel):
        if channel[i] in ["c", "d", "e", "f", "g", "a", "b", "r", "h", "o", "<", ">", "@", "v", "w", "y", "t", "p", "n", "&"]:
            channel = channel[0:i] + " " + channel[i:len(channel)]
            i += 1
        if channel[i] in ["$", "q"]:
            channel = channel[0:i+3] + " " + channel[i+3:len(channel)]
            channel = channel[0:i] + " " + channel[i:len(channel)]
            i += 3
        i += 1
    return channel


# In order to be able to work better in the commands, they are brought
# into a tabular form with this method.
def commands_to_table(channels):
    df = pd.DataFrame()
    for i, channel in enumerate(channels):
        global_time = 0
        instrument = i
        octave = 4
        for cmd in channel.split():
            # if it is a note
            if cmd[0] in ["c", "d", "e", "f", "g", "a", "b"]:
                if len(cmd)>1:
                    if cmd[1] == "+":
                        note = cmd[0:2]
                        duration = cmd[2:len(cmd)]
                    else:
                        note = cmd[0]
                        duration = cmd[1:len(cmd)]
                else:
                    note = cmd[0]
                    duration = cmd[1:len(cmd)]
                key = pitch_to_key(note, octave)
                ticks = value_to_ticks(duration)
                df = pd.concat([df, pd.DataFrame({"global_time":[global_time], "channel":[i], "instrument":[instrument], "key":[key], "ticks":[ticks]})])
                global_time += ticks
            # if it is a rest
            if cmd[0] == "r":
                duration = cmd[1:len(cmd)]
                ticks = value_to_ticks(duration)
                global_time += ticks
            # if it is a octave definition, in- or decrease
            if cmd[0] == "o":
                octave = int(cmd[1:len(cmd)])
            if cmd[0] == ">":
                octave += 1
            if cmd[0] == "<":
                octave -= 1
            # if the instrument ist changing
            if cmd[0] == "@":
                instrument = cmd[1:len(cmd)]
    return df


# Converts the table to a MIDI file
def table_to_midi(table, output, by="instrument"):
    mid = mido.MidiFile()
    mid.ticks_per_beat=48
    iter = np.unique(table[by])
    print(f"found {len(iter)} unique group(s)")
    for x in iter:
        df_filter = table[table[by]==x]
        df = pd.DataFrame()
        for i in range(len(df_filter)):
            key = df_filter.iloc[i].key
            on = df_filter.iloc[i].global_time
            off = on + df_filter.iloc[i].ticks
            df = pd.concat([df, pd.DataFrame({"global_tick":[on], "event":["note_on"], "key":[key]})])
            df = pd.concat([df, pd.DataFrame({"global_tick":[off], "event":["note_off"], "key":[key]})])
        df.reset_index(inplace=True, drop=True)
        df = df.sort_values(["global_tick", "event"], ascending=[True, True])
        df["delta_ticks"] = np.ediff1d(df["global_tick"], to_begin=df["global_tick"].values[0])
        track = mido.MidiTrack()
        track.name = f"{by}_{x}"
        for i in range(len(df)):
            key = df.iloc[i].key
            time = df.iloc[i].delta_ticks
            event = df.iloc[i].event
            try:
                track.append(mido.Message(event, note=key, time=time))
            except:
                print("Could not append event")
        mid.tracks.append(track)
    mid.save(output)


if __name__ == "__main__":
    main(sys.argv[1:])

# for testing only
# main(["-i", "test.mid", "-o", "test.mid_to.mml", "--readable-midi"])
# main(["-i", "test.mml", "-o", "test.mml_to.mid"])