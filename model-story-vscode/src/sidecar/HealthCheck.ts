/**
 * Poll the model-story server health endpoint until it responds.
 */
import * as http from "http";

/**
 * Wait for the server at `url` to return HTTP 200.
 *
 * @param url           Full URL including path, e.g. `http://127.0.0.1:7860/api/health`
 * @param timeoutMs     Maximum wait time in milliseconds (default 10000)
 * @param intervalMs    Poll interval (default 250)
 * @returns             Resolves when server is ready; rejects on timeout.
 */
export function waitReady(
  url: string,
  timeoutMs = 10_000,
  intervalMs = 250,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;

    const attempt = (): void => {
      http
        .get(url, (res) => {
          res.resume(); // drain
          if (res.statusCode === 200) {
            resolve();
          } else {
            scheduleRetry();
          }
        })
        .on("error", scheduleRetry);
    };

    const scheduleRetry = (): void => {
      if (Date.now() + intervalMs > deadline) {
        reject(new Error(`Timed out waiting for server at ${url}`));
        return;
      }
      setTimeout(attempt, intervalMs);
    };

    attempt();
  });
}
