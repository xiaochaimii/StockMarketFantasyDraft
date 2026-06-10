"""Stock trivia, rotating daily per ticker."""

from __future__ import annotations

import datetime
import hashlib

STOCK_TRIVIA = {
    "AAPL": [
        "Apple's first logo featured Isaac Newton sitting under a tree.",
        "The original Apple I computer sold for $666.66.",
        "Apple has more cash reserves than most countries' GDP.",
    ],
    "MSFT": [
        "Microsoft's first product was a BASIC interpreter for the Altair 8800.",
        "Bill Gates' SAT score was 1590 out of 1600.",
        "The name 'Microsoft' is a blend of 'microcomputer' and 'software'.",
    ],
    "AMZN": [
        "Amazon was originally going to be called 'Cadabra' (as in abracadabra).",
        "Jeff Bezos' first office desk was made from a door.",
        "Amazon's first book order was 'Fluid Concepts and Creative Analogies'.",
    ],
    "GOOG": [
        "Google's original name was 'BackRub'.",
        "The first Google Doodle was a Burning Man stick figure in 1998.",
        "'Googol' (the number 10^100) inspired the name Google.",
    ],
    "META": [
        "Facebook was originally limited to Harvard students only.",
        "The iconic blue color was chosen because Zuckerberg is red-green colorblind.",
        "Facebook's 'Like' button was almost called the 'Awesome' button.",
    ],
    "NVDA": [
        "NVIDIA's name comes from 'invidia', the Latin word for envy.",
        "The company was founded in a Denny's restaurant in 1993.",
        "NVIDIA's first product, the NV1, could also play Sega Saturn games.",
    ],
    "NFLX": [
        "Netflix was founded because Reed Hastings got a $40 late fee from Blockbuster.",
        "Netflix's first DVD shipped was 'Beetlejuice' in 1998.",
        "The company considered naming itself 'Kibble' at one point.",
    ],
    "DIS": [
        "Walt Disney was fired from a newspaper for 'lacking imagination'.",
        "Mickey Mouse was originally going to be named 'Mortimer Mouse'.",
        "Disney World is roughly the same size as San Francisco.",
    ],
    "COST": [
        "Costco sells more hot dogs than every MLB stadium combined.",
        "The Costco hot dog combo has been $1.50 since 1985.",
        "Costco's Kirkland Signature is one of the largest brands in the world.",
    ],
    "COIN": [
        "Coinbase was the first crypto company to go public on the Nasdaq.",
        "The company was founded in a two-bedroom apartment in San Francisco.",
    ],
    "AMD": [
        "AMD was founded by Jerry Sanders, a former Fairchild Semiconductor exec.",
        "AMD and Intel were both founded within a year of each other (1968-1969).",
    ],
    "INTC": [
        "Intel's first product was a memory chip, not a processor.",
        "The Intel Inside jingle is one of the most recognized sounds in advertising.",
        "Gordon Moore (of Moore's Law) co-founded Intel.",
    ],
    "WMT": [
        "The first Walmart opened in 1962 in Rogers, Arkansas.",
        "Walmart is the world's largest employer with over 2 million workers.",
    ],
    "BRK-B": [
        "Berkshire Hathaway was originally a textile company.",
        "Warren Buffett bought his first stock at age 11.",
        "Berkshire's Class A shares are the most expensive stock in the world.",
    ],
    "RBLX": [
        "Over half of American kids under 16 play Roblox.",
        "Roblox was originally called 'DynaBlocks' when it launched in 2004.",
    ],
    "MCD": [
        "McDonald's serves about 69 million customers daily worldwide.",
        "The Big Mac was invented by a franchisee, not McDonald's corporate.",
    ],
    "PLTR": [
        "Palantir is named after the seeing stones in Lord of the Rings.",
        "The company was co-founded by Peter Thiel and Alex Karp.",
    ],
    "MSTR": [
        "MicroStrategy holds over 200,000 Bitcoin on its balance sheet.",
        "The company rebranded to 'Strategy' but its ticker is still MSTR.",
    ],
}

GENERIC_TRIVIA = [
    "The stock market has returned an average of about 10% per year since 1926.",
    "The NYSE was founded under a buttonwood tree on Wall Street in 1792.",
    "The term 'bull market' may come from bulls attacking by thrusting horns upward.",
    "The worst single-day crash in history was Black Monday (Oct 19, 1987) — down 22.6%.",
    "Over 90% of day traders lose money according to academic studies.",
    "The S&P 500 has had a positive annual return in about 73% of years since 1926.",
    "Warren Buffett's first stock purchase was at age 11 — he bought Cities Service Preferred.",
    "The word 'stock' comes from the old English word for a tree trunk or block of wood.",
]


def get_daily_trivia(ticker: str) -> str | None:
    """Deterministic-but-daily-rotating trivia for a ticker; None if no entry."""
    facts = STOCK_TRIVIA.get(ticker)
    if not facts:
        return None
    seed = hashlib.md5(f"{ticker}{datetime.date.today().isoformat()}".encode()).hexdigest()
    return facts[int(seed, 16) % len(facts)]


def get_generic_trivia() -> str:
    seed = hashlib.md5(datetime.date.today().isoformat().encode()).hexdigest()
    return GENERIC_TRIVIA[int(seed, 16) % len(GENERIC_TRIVIA)]
