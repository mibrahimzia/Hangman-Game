"""Generate db_init.sql with 5000+ vocabulary words.

Word sources:
  1. Curated category lists below (Animals, Geography, Science, Sports).
  2. The most frequent English words from the `wordfreq` package
     (https://github.com/rspeer/wordfreq, MIT license, built from open
     web/TV corpora). Frequency order keeps the game fun: common words win.

Difficulty is assigned by app.services.word_service.difficulty_for_word so the
stored values always match the documented rule.

One-off build tool: run once, then commit the generated db_init.sql.
Requires: pip install wordfreq

Usage:
    python scripts/seed_words.py      # writes db_init.sql (words)
    python scripts/seed_demo.py       # appends demo scores to db_init.sql
"""

import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.services.word_service import (  # noqa: E402
    MAX_WORD_LEN,
    MIN_WORD_LEN,
    difficulty_for_word,
)

PER_DIFFICULTY = 2200  # 3 x 2200 general words + curated category words
TOP_N = 50000
RANDOM_SEED = 20260913

# Small exact-match blocklist so the game stays classroom-friendly.
BLOCKLIST = {
    "porn",
    "nude",
    "condom",
    "viagra",
    "shit",
    "fuck",
    "bitch",
    "slut",
    "whore",
    "cunt",
    "dick",
    "pussy",
    "boob",
    "boobs",
    "rape",
    "rapist",
    "nazi",
    "hitler",
    "asshole",
    "bastard",
    "dumbass",
    "jackass",
    "penis",
    "vagina",
    "orgasm",
    "fetish",
    "killer",
    "murder",
}

CURATED = {
    "Animals": """
        ant bear beaver bee beetle bison boar buck bull butterfly calf camel
        cat caterpillar chameleon cheetah chicken chipmunk cobra cockroach colt
        coral cow coyote crab crane cricket crocodile crow cub deer dog dolphin
        donkey dove dragonfly duck eagle eel elephant elk falcon ferret finch
        firefly fish flamingo foal fox frog gazelle gecko goose gorilla hamster
        hare hawk hedgehog hen heron hippo horse hyena iguana jaguar jellyfish
        kangaroo kitten koala ladybug lamb lemur leopard lion lizard llama lobster
        lynx mammoth manatee mare mink mole mongoose monkey moose mouse mule
        newt octopus opossum ostrich otter owl oyster panda panther parrot
        peacock pelican penguin pigeon python quail rabbit raccoon ram rat raven
        reindeer rhino robin salmon sardine scorpion seal seahorse shark sheep
        shrew shrimp skunk sloth snail snake sparrow spider squid squirrel starfish
        stork swan tadpole tapir termite tiger toad tortoise trout tuna turkey
        turtle viper vulture walrus wasp whale wolf wolverine wombat worm yak zebra
    """,
    "Geography": """
        atlas bay beach bluff brook canal canyon cape cascade cataract cavern
        channel city cliff coast compass continent country county cove crater creek
        crest delta desert dune equator estuary fjord forest foothill geyser glacier
        globe gorge gulf hamlet harbor headland hill hilltop hollow island islet
        isthmus jungle lagoon lake latitude lava levee longitude lowland magma map
        marsh meadow mesa metropolis mountain ocean oasis outback peninsula plain
        plateau pond pool prairie rapids ravine reef ridge river rivulet rock sandbar
        savanna sea seashore shore slope spring steppe strait stream summit swamp
        tide town tributary tundra valley village volcano waterfall wave wetland woods
        basin border capital north south east west borough cliffside countryside
    """,
    "Science": """
        acid alloy ampere atom axis bacteria base beaker biome bond boron cell
        charge chemical circuit clone comet compound copper core crystal current data
        density diode dose eclipse electron element embryo energy enzyme equation
        ethanol experiment fission flask force fossil fuel galaxy gas gene gravity
        helium hydrogen hypothesis ion iron isotope joule lab laser lens lever light
        liquid litmus lunar magnet mass matter medicine mercury metal meteor microbe
        microscope mineral molecule moon nerve neutron newton nucleus orbit organism
        oxygen ozone particle petal phase photon piston planet plasma prism proton
        pulsar quantum quark radar ray reaction reactor root rust salt satellite scale
        science seed shell soil solar solution solvent spark species spectrum spore
        star static steam steel stem stone storm sulfur sun tendon test theory
        thermometer tissue torque tree trunk vacuum vapor vein volt water wave
        weather weight wire yeast zinc zone
    """,
    "Sports": """
        archery arena athlete backstroke ball base bat batting bicycle bike block
        bowling boxing bunt catch chess coach corner court cricket curling cycling
        dart derby dive dodgeball draw dribble fencing field final foul game goal
        goalie golf guard gymnast half halftime heat helmet hoop hurdles inning jab
        jersey jog judge judo jump kayak kick kickoff lap league lob loss marathon
        match medal mitt net oar offside olympics overtime pace paddle pass pedal
        penalty pitch plate point pole pool puck punt race racket rally referee relay
        ride ring rink rower rowing rugby run runner sail score serve set shot
        sideline skate ski skip sled sprint squash stadium stick stride stroke surf
        swim tackle tag target team tennis tie timer toss track trail trainer
        triathlon trophy umpire vault victory volley warmup whistle win wrestle yoga
    """,
}


def _sql_escape(value: str) -> str:
    return value.replace("'", "''")


_TOKEN_RE = re.compile(r"[a-z]{3,12}")
_JINJA_RE = re.compile(r"{[#{%].*?[#}%]}", re.DOTALL)
_LITERAL_RE = re.compile(r""""([^"\\]{3,200})"|'([^'\\]{3,200})""")


def _reserved_ui_tokens() -> set:
    """Words that appear in UI chrome (templates, CSS/JS, flash/JSON strings).

    These are excluded from the vocabulary so that searching the answer in
    DevTools is unambiguous: any match would be a real leak, never a class
    name, JSON key, or button label.
    """
    reserved = set()
    app_dir = os.path.join(ROOT, "app")
    for dirpath, _dirnames, filenames in os.walk(app_dir):
        for filename in filenames:
            if not filename.endswith((".html", ".css", ".js", ".svg")):
                continue
            with open(os.path.join(dirpath, filename), encoding="utf-8") as handle:
                text = _JINJA_RE.sub(" ", handle.read().lower())
            reserved.update(_TOKEN_RE.findall(text))
    routes_dir = os.path.join(app_dir, "routes")
    for filename in os.listdir(routes_dir):
        if not filename.endswith(".py"):
            continue
        with open(os.path.join(routes_dir, filename), encoding="utf-8") as handle:
            code = handle.read()
        for match in _LITERAL_RE.finditer(code):
            literal = (match.group(1) or match.group(2)).lower()
            reserved.update(_TOKEN_RE.findall(literal))
    return reserved


def _parse_curated():
    words = {}
    for category, blob in CURATED.items():
        for token in blob.split():
            word = token.strip().lower()
            if not word:
                continue
            assert word.isalpha() and word.isascii(), f"bad curated word: {word!r}"
            assert MIN_WORD_LEN <= len(word) <= MAX_WORD_LEN, f"bad length: {word!r}"
            words.setdefault(word, category)  # first category wins on overlap
    return words


def main() -> None:
    from wordfreq import top_n_list

    random.seed(RANDOM_SEED)
    reserved = _reserved_ui_tokens()
    curated_all = _parse_curated()
    curated = {w: c for w, c in curated_all.items() if w not in reserved}

    frequent = top_n_list("en", TOP_N)
    pool = [
        word
        for word in frequent
        if word.islower()
        and word.isalpha()
        and word.isascii()
        and MIN_WORD_LEN <= len(word) <= MAX_WORD_LEN
        and word not in BLOCKLIST
        and word not in curated_all
        and word not in reserved
    ]

    buckets = {"Easy": [], "Medium": [], "Hard": []}
    for word in pool:  # pool stays in frequency order: most common first
        buckets[difficulty_for_word(word)].append(word)

    chosen = []
    for difficulty in ("Easy", "Medium", "Hard"):
        for word in buckets[difficulty][:PER_DIFFICULTY]:
            chosen.append((word, difficulty, "General"))
    for word, category in sorted(curated.items()):
        chosen.append((word, difficulty_for_word(word), category))

    seen = set()
    deduped = []
    for row in chosen:
        if row[0] not in seen:
            seen.add(row[0])
            deduped.append(row)

    out_path = os.path.join(ROOT, "db_init.sql")
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(
            "-- EF101-P01 Hangman seed data. GENERATED by scripts/seed_words.py "
            "(do not hand-edit).\n"
            f"-- {len(deduped)} vocabulary words.\n"
        )
        chunk = []
        for word, difficulty, category in deduped:
            chunk.append(f"('{_sql_escape(word)}', '{difficulty}', '{category}')")
            if len(chunk) >= 500:
                handle.write(
                    "INSERT OR IGNORE INTO words (word, difficulty, category) VALUES\n  "
                    + ",\n  ".join(chunk)
                    + ";\n"
                )
                chunk = []
        if chunk:
            handle.write(
                "INSERT OR IGNORE INTO words (word, difficulty, category) VALUES\n  "
                + ",\n  ".join(chunk)
                + ";\n"
            )

    from collections import Counter

    print(f"wrote {out_path} with {len(deduped)} words")
    print(
        f"reserved UI tokens: {len(reserved)}; curated dropped: {len(curated_all) - len(curated)}"
    )
    print("by difficulty:", dict(Counter(d for _, d, _ in deduped)))
    print("by category:  ", dict(Counter(c for _, _, c in deduped)))
    assert len(deduped) >= 5000, "vocabulary must be >= 5000 words"


if __name__ == "__main__":
    main()
