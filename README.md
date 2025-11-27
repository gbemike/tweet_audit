# tweet-audit

Analyse your X (Twitter) archive using Gemini AI and flag tweets for deletion based on custom criteria.

## Overview

This tool processes your X archive, evaluates each tweet against your alignment criteria (e.g., unprofessional language, specific keywords, outdated opinions), and generates a list of tweet URLs marked for manual deletion.

## The Task

### Goal

Request an archive of your posts on X, analyse them using Google's Gemini AI, and flag tweets for deletion based on any criteria. For instance:

- Posts containing certain words you no longer want associated with you
- Phrases that aren't professional
- Old opinions you've moved on from
- Any custom alignment rules you define

### Output

A CSV file containing flagged tweet URLs and a deletion status flag:

```csv
tweet_url,deleted
https://x.com/username/status/1234567890,false
https://x.com/username/status/9876543210,false
```

You can manually delete these tweets or optionally use the X API for automated deletion.

## Requirements

1. **X Archive**: Download your X archive from Settings → Your Account → Download an archive of your data (takes 24-48 hours)
2. **Gemini API Key**: Get one from [Google AI Studio](https://aistudio.google.com/app/apikey)
3. **Your alignment criteria**: Define what makes a tweet "unaligned" with your current values

## Setup

### 1. Request Your X Archive

1. Go to x.com and log in
2. Navigate to: More → Settings and privacy → Your account → Download an archive of your data
3. Verify your identity
4. Wait 24-48 hours for the email with download link
5. Extract the ZIP file

### 2. Get Gemini API Key

1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create API key
3. Add to your config file (see implementation)

### 3. (Optional) X API Access: OVERKILL, NOT NECESSARY

**Note**: This is overkill for most users. Manual deletion via the CSV output is simpler and free.

If you really want automated deletion:

1. Go to [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Create a Project and App
3. Generate API keys and tokens
4. Use API to delete flagged tweets programmatically

For 99% of use cases, **just delete manually using the CSV output**.

## Implementation

You are free to use:

- Any architectural pattern
- Any programming language
- Any design decisions you see fit

Document your choices in `TRADEOFFS.md` (see below).

## Repository Structure

```
tweet-audit/
├── README.md
├── TRADEOFFS.md          # Your implementation trade-offs (required)
├── .gitignore            # Must ignore archive files and output
├── src/                  # Your implementation
├── tests/                # Your tests (required)
└── config.example.json   # Example config (no real keys)
```

## Critical Requirements

### Testing

**You must include tests.**

Integration tests with actual Gemini API calls are overkill and not neccessary (costs money).

### TRADEOFFS.md

Create a concise document explaining:

- Architecture choices (why this pattern?)
- Concurrency strategy (sequential vs batch vs full async?)
- Error handling approach (retry? fail fast? log and continue?)
- Performance vs safety trade-offs
- Why you chose your specific language/framework

**Keep it under 500 words.**

## Submission

### Code Review Process

**If you need reviews:**

1. Create a private repo (if you don't want comments to be public)
2. Add `benx421` as a collaborator
3. Push your current code to a branch called `review-request` (or similar)
4. Push an empty commit or a README to `main`/`master` branch
5. Create a PR from `review-request` to `main`/`master` branch
6. Request review from `benx421`

When I have time, I will accept the invite and review your code.

## Example Alignment Criteria

```json
{
  "criteria": {
    "forbidden_words": ["crypto", "NFT", "hustlegrindset"],
    "professional_check": true,
    "tone": "respectful and thoughtful",
    "exclude_politics": true
  }
}
```

Pass this to Gemini and construct any prompt you deem fit.
