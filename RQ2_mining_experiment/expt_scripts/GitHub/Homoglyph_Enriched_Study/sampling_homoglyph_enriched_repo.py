import os
import json
import time
import random
from pathlib import Path
from typing import List, Dict, Set, Optional

import requests


NONASCII_TOKENS_PATH = Path("ascii_confusables.json")	# homoglyph list 
TOKENS_PER_RUN = 10	# number of homoglyphs searched per run (to enable checkpoint)
TOKENS_OFFSET = 1731	# start of searching (must change after every run)
MAX_REPOS_PER_TOKEN = 200	# number of repsitories saved per token
PER_PAGE = 100  # pagination
SEARCH_REQUEST_DELAY_SECONDS = 30.0 # to avoid 429 response - secondary limit protection 30 search/min - (2 sec resulted in 429 error too many requests)
DELAY_BOT_DETECTION_RANDOM = 5.0	# to avoid detection as a bot
BASE_BACKOFF_SECONDS = 15.0	# to handle error responses by sleeping incrementaly - (in terms of attempts)

OUTPUT_TOKEN_REPOS_JSONL = Path("token_repo_hits.jsonl")	# output file - list of repos per token - user/reponame (format)
OUTPUT_REPOS_JSONL = Path("repos_for_cloning.jsonl")	# output file -  for cloning



# Function for loading homoglyph token from the json file (homoglyph list)

def load_tokens(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Cannot find token file at {path}")

    with path.open("r", encoding="utf-8") as f:	# to avoid UnicodeDecodeError, UTF-8 - standard encoding for mordern text files, supports unicode chars
        tokens = json.load(f)

    tokens = [str(t) for t in tokens]
    print(f"Loaded {len(tokens)} homoglyph tokens from {path}")
    return tokens


# Function to decide the time to sleep

def compute_sleep_until_reset(reset_epoch: int) -> float:
    now = time.time()
    delta = reset_epoch - now
    if delta < 0:
        return 5.0
    return delta + 5.0  # add 5s for safety


# Function to convert epoch seconds to human readable form

def format_utc_from_epoch(epoch: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(epoch))


# Function to sleep if X-RateLimit remaining is at 1 ( to avoid 403)

def sleep_for_rate_limit(
    remaining_int: Optional[int],
    reset_int: Optional[int],
    desc: str,
) -> None:	# remaining_int - how many requests left, reset_int - github reset
    if remaining_int is None or reset_int is None:
        return

    if remaining_int <= 1:
        sleep_sec = compute_sleep_until_reset(reset_int)
        reset_str = format_utc_from_epoch(reset_int)
        print(
            f"-----Approaching core rate limit after {desc}-----"
            f"(remaining={remaining_int}). "
            f"Going to sleep mode until {reset_str} ({sleep_sec:.1f}s)."
        )
        print("Sleeping(rate limit)...")
        time.sleep(sleep_sec)
        print("Waking Up...")


# Function to include random delay before each API call to avoid secondary rate limit. Random delay added to avoid bot detection (429 response)

def safe_delay(desc: str) -> None:
    delay = SEARCH_REQUEST_DELAY_SECONDS + random.random() * DELAY_BOT_DETECTION_RANDOM
    print(f"Waiting {delay:.1f}s before request ({desc})")
    time.sleep(delay)


# Function to find repository containing tokens

def github_search_code_for_token(
    session: requests.Session,
    github_token: str,
    token_str: str,
    max_repos: int,
) -> Set[str]:

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Homoglyph-Research-Academic/1.0",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    collected_repos: Set[str] = set()
    page = 1
    attempt = 0

    while len(collected_repos) < max_repos:
        desc = f"search_code token={repr(token_str)} page={page}"
        safe_delay(desc)

        params = {
            "q": f'"{token_str}" in:file',
            "per_page": PER_PAGE,
            "page": page,
        }

        attempt += 1

        try:
            resp = session.get(
                "https://api.github.com/search/code",
                headers=headers,
                params=params,
                timeout=30,
            )
        except requests.RequestException as e:
            backoff = BASE_BACKOFF_SECONDS * attempt
            print(f"Client error on {desc}: {e}. Backing off {backoff:.1f}s and retrying.")
            print("..........Sleeping.........")
            time.sleep(backoff)
            print("..........Waking up..........")
            continue

        status = resp.status_code
        text = resp.text

        # Reading rate limit headers of responses
        rl_remaining = resp.headers.get("X-RateLimit-Remaining")
        rl_reset = resp.headers.get("X-RateLimit-Reset")
        remaining_int: Optional[int] = None
        reset_int: Optional[int] = None
        try:
            if rl_remaining is not None:
                remaining_int = int(rl_remaining)
            if rl_reset is not None:
                reset_int = int(rl_reset)
        except ValueError:
            pass

        # Response - 200
        if status == 200:
            try:
                data = resp.json()
            except json.JSONDecodeError:
                backoff = BASE_BACKOFF_SECONDS * attempt
                print(f".....JSON decode error on {desc}: {text[:200]}.....")
                print(f".....Backing off {backoff:.1f}s before retrying.....")
                print(".....Sleeping.....")
                time.sleep(backoff)
                print(".....Waking up.....")
                continue

            items = data.get("items", [])
            if not items:	# No more results.
                sleep_for_rate_limit(remaining_int, reset_int, desc)
                break

            for item in items:
                repo = item.get("repository") or {}
                full_name = repo.get("full_name")
                if full_name:
                    collected_repos.add(full_name)
                    if len(collected_repos) >= max_repos:
                        break

            sleep_for_rate_limit(remaining_int, reset_int, desc)	# remaining <= 1.

            
            if len(items) < PER_PAGE or len(collected_repos) >= max_repos:	# if no more pages
                break

            page += 1	# move to next page.
            attempt = 0  # reset attempt counter on success
            continue

        # Response - 401
        elif status == 401:
            print(f"401 Unauthorized on {desc}. Check your GITHUB_TOKEN.")
            # This is a fatal error for the whole run.
            raise SystemExit("GITHUB_TOKEN invalid or missing (401 Unauthorized).")

        # Response - 400
        elif status == 400:
            print(f"400 Bad Request on {desc}. Response: {text[:200]}...")
            print("Skipping this token due to malformed query.")
            break

        # Response - 403
        elif status == 403:
            lower_msg = text.lower()
            print(f"403 on {desc}. Snippet: {text[:200]}...")

            # Core rate limit exceeded.
            if "rate limit exceeded" in lower_msg:
                if reset_int is not None:
                    sleep_sec = compute_sleep_until_reset(reset_int)
                    reset_str = format_utc_from_epoch(reset_int)
                    print(
                        f".....Core rate limit exceeded on {desc}......"
                        f"Going to sleep until {reset_str} ({sleep_sec:.1f}s)."
                    )
                    print(".....Sleeping.....")
                    time.sleep(sleep_sec)
                    print(".....Waking Up.....")
                    attempt = 0
                    continue
                else:
                    backoff = BASE_BACKOFF_SECONDS * attempt
                    print(
                        f"Core rate limit exceeded..... "
                        f"Backing off {backoff:.1f}s before retrying."
                    )
                    print("......Sleeping.....")
                    time.sleep(backoff)
                    print(".....Waking Up.....")
                    continue

            # Response - 403  or Search abuse detection
            else:
                backoff = (BASE_BACKOFF_SECONDS * attempt) * 3600.0
                print(
                    f".....Abuse detection on {desc}..... "
                    f"Backing off {backoff:.1f}s before retrying."
                )
                print(".....Sleeping.....")
                time.sleep(backoff)
                print(".....Waking Up.....")
                continue

        # Response - 404
        elif status == 404:
            print(f".....404 Not Found on {desc}. Response: {text[:200]}.....")
            print("Skipping this token.")
            break

        # Response - 408
        elif status == 408:
            if attempt >= 3:
                print(f"408 timeout on {desc} after {attempt} attempts. Giving up for this token.")
                break
            backoff = BASE_BACKOFF_SECONDS * attempt
            print(f"408 timeout on {desc}. Backing off {backoff:.1f}s and retrying.")
            print(".....Sleeping.....")
            time.sleep(backoff)
            print(".....Waking Up.....")
            continue

        # Response - 422
        elif status == 422:
            print(f"422 Unprocessable Entity on {desc}. Response: {text[:200]}...")
            print("This token is not supported by search. Skipping this token.")
            break

        # Response - 429
        elif status == 429:
            if attempt >= 3:
                print(f"429 Too Many Requests on {desc} after {attempt} attempts. Giving up for this token.")
                break
            backoff = (BASE_BACKOFF_SECONDS * attempt) + 1500.0
            print(f"429 Too Many Requests on {desc}. Backing off {backoff:.1f}s and retrying.")
            print(".....Sleeping...")
            time.sleep(backoff)
            print(".....Waking Up.....")
            continue

        # Response - 409
        elif status == 409:
            backoff = BASE_BACKOFF_SECONDS * attempt
            print(
                f".....409 Conflict on {desc}..... "
                f"Temporary backend state. Backing off {backoff:.1f}s and retrying."
            )
            print(".....Sleeping.....")
            time.sleep(backoff)
            print(".....Waking Up.....")
            continue

        # Response - 5xx server err
        elif 500 <= status < 600:
            backoff = BASE_BACKOFF_SECONDS * attempt
            print(
                f".....server error on {desc}....."
                f"Backing off {backoff:.1f}s and retrying."
            )
            print(".....Sleeping.....")
            time.sleep(backoff)
            print(".....Waking Up.....")
            continue

        # Response - 4xx
        else:
            print(f".....Unexpected {status} on {desc}. Body: {text[:200]}.....")
            sleep_for_rate_limit(remaining_int, reset_int, desc)
            break

    return collected_repos






def main():
    all_tokens = load_tokens(NONASCII_TOKENS_PATH)	# Load a batch of tokens

    start = TOKENS_OFFSET
    end = min(len(all_tokens), TOKENS_OFFSET + TOKENS_PER_RUN - 1)
    tokens = all_tokens[start:end + 1]

    if not tokens:
        raise ValueError("............No More Tokens............")

    print(f"Using tokens [{start}:{end}] → {len(tokens)} tokens in this run.")

    github_token = os.environ.get("GITHUB_TOKEN", "").strip()	# Github token
    if not github_token:
        print("...........Warning!! No GITHUB_TOKEN set...............")

	# Output files - append mode
    token_repos_f = OUTPUT_TOKEN_REPOS_JSONL.open("a", encoding="utf-8")
    repos_to_clone_f = OUTPUT_REPOS_JSONL.open("a", encoding="utf-8")

    repo_to_tokens: Dict[str, Set[str]] = {}	# Dictionary to avoid duplication.......

    with requests.Session() as session:		# Searching serially for token
        for idx, token_str in enumerate(tokens, start=1):
            print(f"\n ({idx}/{len(tokens)}) Searching for token: {repr(token_str)}")

            repos_for_token = github_search_code_for_token(
                session=session,
                github_token=github_token,
                token_str=token_str,
                max_repos=MAX_REPOS_PER_TOKEN,
            )

            print(f"Result...........token={repr(token_str)} → {len(repos_for_token)} repos")


            token_entry = {
                "token": token_str,
                "repos": sorted(repos_for_token),
            }
            token_repos_f.write(json.dumps(token_entry, ensure_ascii=False) + "\n")
            token_repos_f.flush()


            for full_name in repos_for_token:
                repo_to_tokens.setdefault(full_name, set()).add(token_str)


    for full_name, tokens_hit in repo_to_tokens.items():
        repo_entry = {
            "full_name": full_name,
            "tokens_hit": sorted(tokens_hit),
        }
        repos_to_clone_f.write(json.dumps(repo_entry, ensure_ascii=False) + "\n")

    token_repos_f.close()
    repos_to_clone_f.close()

    print("\n..........sampling completed for this batch of tokens..............")
    print(f"       Token→repos appended to: {OUTPUT_TOKEN_REPOS_JSONL}")
    print(f"       Repo→tokens appended to: {OUTPUT_REPOS_JSONL}")


if __name__ == "__main__":
    main()

