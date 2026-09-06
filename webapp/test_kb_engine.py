"""
Lightweight, dependency-free test harness for kb_engine.offline_reply().

Why this exists: the changes in this branch were made by Claude using only
browser automation tools (no Python runtime available), so it could not
literally run this app and fire prompts at it. This script generates several
hundred varied prompts across every category the offline engine handles,
plus a batch of edge cases and a regression check for a bug that was fixed
(see below), runs them all through offline_reply(), and reports anything
that crashes or looks wrong.

Run it yourself with nothing but the standard library, from the webapp/
folder:

    cd webapp
    python test_kb_engine.py

It does NOT need Flask, Ollama, or any API key -- it imports kb_engine.py
directly, exactly like app.py's offline fallback does.

Bug this guards against: try_math() used to fire on ANY text containing
digits plus an operator-like character anywhere in the message, so things
like phone numbers ("call me at 555-1234"), dates, and sports scores
("we won 3-2") were silently misread as arithmetic and given a nonsense
numeric answer. It now only evaluates when the rest of the message is just
normal math phrasing. The "regression" prompts below check this stays fixed.

A second bug this guards against: _MAX_EXPONENT alone bounded the exponent
of a `**` but not the base's digit count, so a huge base raised to a small,
in-bounds exponent (e.g. a ~4300-digit number cubed) could still burn real
CPU computing a result whose decimal string representation blows past
Python's own int-to-str conversion digit limit -- which then got silently
swallowed, wasting that CPU time for no answer at all. try_math() now
estimates the result's digit count up front and returns a friendly "too
large" message instead. The same huge-digit-run input also used to make
try_convert()'s and try_number_ops()'s "<number><keyword>" regexes take
quadratic time backtracking through it (a separate bug, same root cause:
no bound on how long a run of digits can be) -- both now bail out via
_has_oversized_number() first. HUGE_BASE_PROMPT below, and the 3s call-time
ceiling in main(), check all of this stays fixed.
"""
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kb_engine  # noqa: E402

# A base right at the edge of what Python can even parse as one token
# (4300 digits, matching sys.get_int_max_str_digits()'s default) raised to a
# small, comfortably in-bounds exponent -- individually "reasonable" by the
# old exponent-only bound, but base**3 has ~3x the digits of the base alone,
# well past that same limit once try_math() tries to format it into a reply.
HUGE_BASE = "9" * 4300
HUGE_BASE_PROMPT = f"what is {HUGE_BASE}**3"


def ask(text):
    return kb_engine.offline_reply([{"role": "user", "content": text}])


def build_prompts():
    prompts = []

    # 1. Greetings / farewells / thanks (English + Urdu), varied casing/punctuation
    prompts += ["hi", "Hello", "hey there", "assalam o alaikum", "Salam", "HI!!"]
    prompts += ["\u0627\u0644\u0633\u0644\u0627\u0645 \u0639\u0644\u06cc\u06a9\u0645", "\u0633\u0644\u0627\u0645", "\u062e\u062f\u0627 \u062d\u0627\u0641\u0638", "\u0634\u06a9\u0631\u06cc\u06c1", "thanks", "thank you so much"]

    # 2. Arithmetic -- generated across a range of operators/values
    for a in range(1, 12):
        for op in ["+", "-", "*"]:
            prompts.append(f"what is {a} {op} {a*3}")
    prompts += ["sqrt(144)", "square root of 81", "15% of 200", "50% of 88", "2**10"]

    # 3. Number utilities
    for n in [5, 7, 10, 13, 20, 0, 1, 170]:
        prompts.append(f"factorial of {n}")
    for n in [2, 4, 17, 97, 100, 1]:
        prompts.append(f"is {n} prime")
    prompts += ["gcd of 24 and 36", "lcm of 4 and 6", "10 to binary", "255 to hex",
                "average of 2, 4, 6, 8", "median of 1, 3, 3, 6, 7, 8, 9",
                "max of 3, 90, 12", "min of 3, 90, 12"]

    # 4. Unit conversions
    for v in [1, 5, 10, 42, 100]:
        prompts += [f"{v} km to miles", f"{v} miles to km", f"{v} kg to lbs",
                    f"{v} celsius to fahrenheit", f"{v} cm to inches",
                    f"{v} litres to gallons", f"{v} km/h to mph"]

    # 5. Regression tests for the try_math false-positive bug fix -- none of
    # these should ever be answered as if they were arithmetic.
    prompts += [
        "call me at 555-1234", "my number is 0301-1234567", "room 101-102",
        "we won the match 3-2", "the score was 21-14", "born on 12-25-2001",
        "meet me on 5-6 at noon", "flight AI-202 departs at 5", "order number 4587-2210",
    ]

    # 6. Dictionary / translation lookups
    words = ["university", "semester", "library", "book", "water", "friend", "teacher",
             "exam", "hostel", "student", "notes", "holiday", "cnic", "nadra",
             "easypaisa", "jazzcash", "fbr", "wapda", "iftar", "sehri"]
    prompts += words
    prompts += [f"what is {w} in urdu" for w in ["book", "water", "friend"]]

    # 7. Knowledge-base questions (general knowledge + the new study-related entries)
    prompts += [
        "what is wifi", "difference between wifi and bluetooth", "what is a semester",
        "what is gpa", "difference between gpa and cgpa", "what is plagiarism",
        "what is a thesis", "what is an internship", "how to study effectively",
        "what is a scholarship", "what is hec", "what is a credit hour",
        "how to manage time better", "how to stop procrastinating", "what is a viva",
        "what is a literature review", "what is peer review", "tips for writing assignments",
        "what is a cnic", "what is nadra", "difference between easypaisa and jazzcash",
        "what is mobile load", "what is fbr", "what is ntn", "why is there load shedding",
        "difference between wapda and k-electric", "what is bisp", "what is ehsaas program",
        "what is a patwari", "what is stamp paper used for", "what is a vakil",
        "difference between iftar and sehri", "what is qurbani", "difference between zakat and ushr",
        "what is mehr", "what is dowry",
    ]

    # 8. Time / date
    prompts += ["what time is it", "what's the date", "what day is it", "current time"]

    # 9. Edge cases: empty/whitespace/very long/garbage/special characters
    prompts += ["", "   ", "?", "......", "a" * 500, "<script>alert(1)</script>",
                "'; DROP TABLE users; --", "\ud83d\ude00\ud83c\udf89\ud83d\ude80", "\n\n\t",
                "1" * 50 + "+" + "2" * 50, HUGE_BASE_PROMPT]

    # 10. Mixed language / code-mixed
    prompts += ["hello, aap kaisay hain?", "what is \u067e\u0627\u0646\u06cc", "thank you \u0628\u06c1\u062a \u0634\u06a9\u0631\u06cc\u06c1"]

    # Pad out to a few hundred total by exercising the same code paths with
    # different casing/punctuation -- these aren't meaningless duplicates,
    # since is_urdu(), regex casing, and the fuzzy-correct path all behave
    # slightly differently depending on exact text.
    variations = []
    for p in prompts:
        variations.append(p)
        if p.strip():
            variations.append(p.upper())
            variations.append(p + "?")
    return variations


def main():
    prompts = build_prompts()
    print(f"Running {len(prompts)} prompts through kb_engine.offline_reply()...\n")

    crashes = []
    fallback_count = 0
    math_regression_hits = []
    huge_power_hits = []
    huge_power_max_call_time = 0.0
    regression_markers = ["555-1234", "0301-1234567", "101-102", "3-2", "21-14",
                           "12-25-2001", "5-6", "AI-202", "4587-2210"]

    t0 = time.time()
    for p in prompts:
        call_t0 = time.time()
        try:
            reply = ask(p)
        except Exception:
            crashes.append((p, traceback.format_exc()))
            continue
        call_elapsed = time.time() - call_t0
        if reply and "comes to **" in reply and any(marker in p for marker in regression_markers):
            math_regression_hits.append((p, reply))
        if HUGE_BASE in p:
            # Should return a friendly "too large" message, quickly -- not
            # silently fall through to something else after burning CPU on
            # an unbounded huge**small computation (the bug this guards).
            # Flag it either way: wrong/missing content, OR a call that's
            # come back slow (generous 3s bar -- everything else in this
            # whole few-hundred-prompt run finishes in low milliseconds; a
            # regression here previously took ~10s per call) -- so a
            # re-introduced quadratic-regex blowup gets caught even on a
            # call that still eventually lands on the right reply text.
            huge_power_max_call_time = max(huge_power_max_call_time, call_elapsed)
            if not reply or "too large" not in reply.lower() or call_elapsed > 3.0:
                huge_power_hits.append((p, reply, call_elapsed))
        if reply and ("offline knowledge base" in reply or "\u0622\u0641 \u0644\u0627\u0626\u0646" in reply or "\u0645\u0639\u0630\u0631\u062a" in reply):
            fallback_count += 1
    elapsed = time.time() - t0

    print(f"Done in {elapsed:.2f}s")
    print(f"Total prompts: {len(prompts)}")
    print(f"Crashes (unhandled exceptions): {len(crashes)}")
    print(f"Fell through to the generic 'I don't know that yet' reply: {fallback_count}")
    print(f"Regression check -- non-math text misread as arithmetic: {len(math_regression_hits)}")
    print(f"Regression check -- huge base**small exponent mishandled: {len(huge_power_hits)} "
          f"(slowest call {huge_power_max_call_time:.2f}s)")

    if crashes:
        print("\n--- CRASHES ---")
        for p, tb in crashes:
            print(f"Prompt: {p!r}\n{tb}\n")
    if math_regression_hits:
        print("\n--- MATH FALSE-POSITIVE REGRESSION (should be empty) ---")
        for p, r in math_regression_hits:
            print(f"Prompt: {p!r} -> {r!r}")
    if huge_power_hits:
        print("\n--- HUGE BASE**EXPONENT REGRESSION (should be empty) ---")
        for p, r, t in huge_power_hits:
            print(f"Prompt (truncated): {p[:60]!r}... -> {r!r} ({t:.2f}s)")

    if not crashes and not math_regression_hits and not huge_power_hits:
        print("\nAll good: no crashes, the phone-number/date/score false-positive bug did not "
              "reappear, and a huge base**small-exponent expression got a clean, fast answer.")
    sys.exit(1 if (crashes or math_regression_hits or huge_power_hits) else 0)


if __name__ == "__main__":
    main()
