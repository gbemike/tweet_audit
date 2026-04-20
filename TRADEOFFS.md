## **Architecture: Parallel Batch Processing**

The tool uses a shell script as an orchestrator that spawns N (which corresponds to the number of chunks in our config) parallel workers, each independently running its own process. The script launches the workers, monitors their status, and merges the resulting chunks. The data isn't processed sequentially; instead, it's split into N chunks, and each chunk is processed independently and in parallel via the shell script. Sequential processing can take about 2 hours for 3,000 tweets. With 5 parallel chunks, runtime drops to roughly 5 minutes, a 24x speedup.

Google's Batch API was used over the real-time API for two main reasons: the Batch API is 50% cheaper, and it allows for higher throughput, which is why the parallel approach suited this use case. The major drawback is that the Batch API doesn't support JSON schema enforcement for batch file requests, unlike the real-time API. Additionally, the Batch API has inconsistencies in its response format. This means about 1–5% of responses may be malformed (missing fields or incorrect format). To mitigate corruption, the tool uses strict prompt engineering (with explicit JSON examples) and logs malformed responses for manual review. Additionally, the Batch API is only available on a tiered API key, so users would need a paid API key to run the tool.

## Clean Fail

During failures, the `failed_ids` are saved for inspection. After one run, if any tweets fail to be processed due to parsing errors, the tool must be rerun. Because of the cache, only tweets that aren't already cached will be processed, which helps immediately filter out processed tweets from unprocessed ones. The main drawback is that if, on rerun, only 1 or 2 tweets need to be processed, the Batch API is still used, which is not ideal.

## **Language Choice: Python**

Python is used in the project primarily for its strong ecosystem and development speed, leveraging its first-class SDK for Google's GenAI Batch API, along with efficient libraries for JSON, CSV, and file handling (like `pathlib` and dataclasses). However, Python is an interpreted language, meaning it runs line by line. Unlike compiled languages, the shell script must launch and initialize a completely separate Python interpreter for each of the N workers. This can cause startup overhead for every single chunk, slowing down the overall process. For a pipeline with such short runtimes, the cumulative time spent just loading the interpreter and modules becomes a non-trivial portion of the total execution time.
