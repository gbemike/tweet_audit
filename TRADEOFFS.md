## **Architecture: Parallel Batch Processing**

The tool uses a shell script as an orchestrator that spawns N (which corresponds to the number of chunks in our config) parallel workers, each independently running its own process. The script launches the workers, monitors their status, and merges the resulting chunks. The data isn't processed sequentially; instead, it's split into N chunks, and each chunk is processed independently and in parallel via the shell script. Sequential processing can take about 2 hours for 3,000 tweets. With 5 parallel chunks, runtime drops to roughly 5 minutes, a 24x speedup.

Google's Batch API was used over the real-time API for two main reasons: the Batch API is 50% cheaper and it allows for higher throughput, hence why the parallel approach suited the API use. The major drawback is that the Batch API doesn't support JSON schema enforcement for batch file requests, unlike the real-time API. Additionally, the Batch API also has inconsistencies in it's response format. This means about 1–5% of responses may be malformed (missing fields or incorrect format), to mitigate and lessen any corruption, strict prompt engineering (using explicit JSON examples) and logging malformed responses for manual reviews are implemented within the tool. Additionally the Batch API is only available on a tiered API key, users would have to get a paid api key to run the tool.

Additionally, Gemini's Batch API handles the internal async operations and queuing, meaning the main overhead is simply waiting on their computation to complete. Speed was prioritized because tweet auditing is a one-time bulk operation, not a real-time service.

[Updated tradeoff] - on retry if only 2 ids fail, retry would run these 2 ids via the batch api which isn't ideals

[changes] - made cache persistently part of the process

## **Fail Fast**

The design ensures that each worker exits immediately on any failure, such as an invalid chunk ID, a batch processing timeout, or a storage error. The shell script, acting as the supervisor, detects these individual chunk failures and immediately aborts the final merge process. This prevents the merging of incomplete or corrupted data. Prioritizing choose data integrity over partial success.The risk of merging partial data is silent loss of information. However, failed chunks can be easily rerun individually later, as the successfully processed chunks are already cached.

## **Language Choice: Python**

Python is used in the project primarily for its strong ecosystem and development speed, leveraging it's first-class Python SDK for Google's GenAI Batch API, along with efficient libraries for JSON, CSV, and file handling (like `pathlib` and data classes). However, Python is an interpreted language, meaning it runs line by line unlike other compiled languages, the shell script must launch and initialize a completely separate Python interpreter for each of the N workers. This can cause startup overhead for every single chunk, slowing down the overall process. For a pipeline with such short runtimes, the cumulative time spent just loading the interpreter and modules becomes a non-trivial portion of the total execution time.
