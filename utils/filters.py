FILTERS = {
    "tremolo": {
        "string": "tremolo=d={depth}:f={frequency}",
        "default_values": {
            "depth": "0.5",
            "frequency": "5"
        },
        "type": "multiple"
    },
    "vibrato": {
        "string": "vibrato=d={depth}:f={frequency}",
        "default_values": {
            "depth": "0.5",
            "frequency": "5"
        },
        "type": "multiple"
    },
    "volume": {
        "string": "volume=volume={}",
        "type": "single"
    },
    "reverse": {
        "string": "areverse",
        "type": "boolean"
    },
    "subboost": {
        "string": "asubboost=dry={dry}:wet={wet}:decay={decay}:feedback={feedback}:cutoff={cutoff}:slope={slope}:delay={delay}",
        "type": "multiple",
        "default_values": {
            "dry": "0.5",
            "wet": "0.8",
            "decay": "0.7",
            "cutoff": "100",
            "slope": "0.5",
            "feedback": "0.5",
            "delay": "20"
        }
    },
    "pad": {
        "string": "apad=pad_dur={}",
        "type": "single"
    },
    "trim": {
        "string": "atrim=start={start}:end={end}",
        "default_values": {
            "start": "2",
            "end": "10",
        },
        "type": "multiple"
    },
    "pitchtempo": {
        "string": "rubberband=tempo={tempo}:pitch={pitch}:pitchq=consistency",
        "default_values": {
            "tempo": 1,
            "pitch": 1
        },
        "type": "multiple"
    }
}