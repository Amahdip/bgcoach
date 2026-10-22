"""Persian explanations of why the best play is best, written by Claude from
the measured facts in facts.py and cached per (position, compared play).
Without an API key, app.py falls back to explain_fa (fixed templates)."""
import json

import anthropic

MODEL = "claude-opus-5-5"

SYSTEM = """You are a backgammon coach explaining a checker play to a Persian-speaking student.

You get JSON facts computed by a program and the gnubg engine for two plays in the same position:
"best" (the engine's choice) and "other" (the student's play, or the runner-up when the student
already found the best play).

Write 3 to 5 short sentences in Persian (Farsi) explaining why "best" is better than "other".
- Use only the facts given. Never invent numbers, plans or positions that are not in the facts.
- Focus on the one or two differences that matter most, such as hits, blots and how many of the
  opponent's 36 rolls hit them, points made or given up, primes, anchors, and the change in
  winning or gammon chances. Skip facts that are the same for both plays.
- Write moves exactly as given (for example 8/5 6/5) and use Western digits.
- Percentages: write chances as whole percents (0.551 -> 55%).
- If the student found the best play, start by saying so in a few words.
- Plain prose: no headings, no lists, no markdown."""


class Unavailable(Exception):
    """No credentials, or the API could not be reached."""


_client = None


def client():
    global _client
    if _client is None:
        try:
            _client = anthropic.AsyncAnthropic()
        except anthropic.AnthropicError as e:  # no credentials configured
            raise Unavailable(str(e))
    return _client


def cached(conn, position_id, other_move):
    row = conn.execute(
        "select text from explanations where position_id = ? and other_move = ? and lang = 'fa'",
        (position_id, other_move),
    ).fetchone()
    return row[0] if row else None


async def write(facts):
    try:
        response = await client().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            # On a policy decline, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
        )
    except TypeError as e:
        # Raised at request time when no API key / auth token / profile is configured.
        if "authentication method" not in str(e):
            raise
        raise Unavailable("no Claude API credentials (set ANTHROPIC_API_KEY or run `ant auth login`)")
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        raise Unavailable(f"Claude API credentials were rejected: {e.message}")
    except anthropic.APIConnectionError:
        raise Unavailable("Couldn't reach the Claude API")
    except anthropic.APIStatusError as e:
        raise Unavailable(f"Claude API error {e.status_code}: {e.message}")
    if response.stop_reason == "refusal":
        raise Unavailable("Claude declined to write this explanation")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise Unavailable("Claude returned no text")
    return text, response.model


def store(conn, position_id, other_move, text, model):
    conn.execute(
        """insert or replace into explanations (position_id, other_move, lang, text, model)
           values (?, ?, 'fa', ?, ?)""",
        (position_id, other_move, text, model),
    )
    conn.commit()
